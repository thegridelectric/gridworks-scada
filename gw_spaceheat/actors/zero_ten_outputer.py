"""One 0-10V output as an actuator: a leaf of the command tree that takes
AnalogDispatch from its boss and drives a level."""

import asyncio
import time
import uuid
from typing import NamedTuple, Sequence

from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto.message import Message
from result import Ok, Result

from actors.sh_node_actor import ShNodeActor
from drivers import gp8403, mcp4728
from scada_app_interface import ScadaAppInterface
from sema_to_dc import zero_ten_power_on_volts_times_ten

from gwsproto.data_classes.components import I2cDacOutputComponent
from gwsproto.data_classes.sh_node import ShNode
from actors import command_reply
from gwsproto.enums import ActorClass, I2cDacChannel, I2cDacType, ScadaCmdRefusalReason
from gwsproto.named_types import (
    ActuatorsReady,
    AnalogDispatch,
    DacOutputConfig,
    I2cReadBytes,
    I2cRegAddress,
    I2cResult,
    I2cWriteByte,
    I2cWriteReg,
    SingleReading,
)

CHANNEL_INDEX = {
    I2cDacChannel.A: 0,
    I2cDacChannel.B: 1,
    I2cDacChannel.C: 2,
    I2cDacChannel.D: 3,
}

# AnalogDispatch.Value for a 0-10V output is volts times ten, 0-100 — the
# unit the VoltsTimesTen channel reports.
VOLTS_TIMES_TEN_MAX = 100


class DacFacts(NamedTuple):
    """What the outputer needs from the choice of DAC chip: the terminal
    volts at full code and whether the chip stores a power-on value. Driver
    facts, keyed on the board record's DacType; not vocabulary."""

    codes: int
    full_scale_volts: float
    supports_power_on_store: bool


DAC_FACTS: dict[I2cDacType, DacFacts] = {
    I2cDacType.Mcp4728: DacFacts(
        mcp4728.CODES, mcp4728.FULL_SCALE_VOLTS, mcp4728.SUPPORTS_POWER_ON_STORE
    ),
    I2cDacType.Gp8403: DacFacts(
        gp8403.CODES, gp8403.FULL_SCALE_VOLTS, gp8403.SUPPORTS_POWER_ON_STORE
    ),
}


def code_from_volts_times_ten(value: int, facts: DacFacts) -> int:
    """The code that drives `value` (volts times ten) at the terminal,
    clamped to the chip's top code: full scale rounds to `codes`, one past
    the last 12-bit code, and the encoders mask that to 0."""
    return min(
        round(value / 10 / facts.full_scale_volts * facts.codes), facts.codes - 1
    )


def volts_times_ten_from_code(code: int, facts: DacFacts) -> int:
    return round(code / facts.codes * facts.full_scale_volts * 10)


class ZeroTenOutputer(ShNodeActor):
    """
    One channel of a board DAC, resolved from the component's board record
    (DacName -> address, mux, chip) and driven through the I2cBus single
    owner. The power-on level comes from the ops word (zero.ten.power.on).
    The chip branch is the driver's: where the chip stores a power-on value
    (MCP4728), boot verifies its EEPROM against that level and reprograms
    only on a mismatch (Single Write: the one EEPROM-touching path); a chip
    that stores nothing (GP8403) gets its output range set once at boot and
    sits at the chip default until the first assert. Then the target level
    — the power-on level until the first dispatch, the last commanded level
    after — is re-asserted every heartbeat and on every dispatch. A
    successful write reports the level on the output's channel.
    """

    HEARTBEAT_S = 60

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self.bus_op_timeout_s = 1.0
        self.pending_results: dict[str, "asyncio.Future[I2cResult]"] = {}
        self.stop_requested = False
        # the chip's one-time boot step done: EEPROM verified (MCP4728) or
        # output range set (GP8403); retried each heartbeat until it is
        self.chip_ready = False
        self.active_warning_keys: set[str] = set()
        self.wake = asyncio.Event()

        component = self.node.component
        if not isinstance(component, I2cDacOutputComponent):
            raise ValueError(
                f"{self.name} expected I2cDacOutputComponent, got {type(component)}"
            )
        self.dac: I2cDacOutputComponent = component
        self.resolve_dac(component)

    def resolve_dac(self, component: I2cDacOutputComponent) -> None:
        """DacName resolved against THIS component's board record — the
        record's DAC list holds the physical address and mux position; the
        layout never restates it."""
        config = component.gt.ConfigList[0]
        if config.ActorName != self.name:
            raise ValueError(
                f"{self.name}: component config names actor {config.ActorName}"
            )
        self.config: DacOutputConfig = config
        self.channel: int = CHANNEL_INDEX[config.DacChannel]
        record = component.board_component.device_type
        dac = next(
            (d for d in record.Dacs if d.DacName == component.gt.DacName), None
        )
        if dac is None:
            raise ValueError(
                f"{self.name}: board record {record.DeviceType} has no DAC "
                f"named {component.gt.DacName}"
            )
        self.dac_address: int = dac.I2cAddress
        if self.channel >= dac.Channels:
            raise ValueError(
                f"{self.name}: channel {config.DacChannel.value} is beyond the "
                f"{dac.Channels} channels of DAC {dac.DacName}"
            )
        self.dac_type: I2cDacType = dac.DacType
        self.facts: DacFacts = DAC_FACTS[dac.DacType]
        if dac.MuxName is not None:
            mux = next(m for m in record.Muxes if m.MuxName == dac.MuxName)
            self.mux_address: int | None = mux.I2cAddress
            self.mux_channel: int | None = dac.MuxChannel
        else:
            self.mux_address = None
            self.mux_channel = None
        bus_nodes = [
            n for n in self.layout.nodes.values() if n.ActorClass == ActorClass.I2cBus
        ]
        if len(bus_nodes) != 1:
            raise ValueError(
                f"{self.name}: expected exactly one I2cBus node in the "
                f"layout; found {len(bus_nodes)}"
            )
        self.bus_node: ShNode = bus_nodes[0]
        # The code the heartbeat drives: the ops word's power-on level until
        # the first dispatch, the last commanded level after.
        self.power_on_code: int = code_from_volts_times_ten(
            zero_ten_power_on_volts_times_ten(self.ops, self.name), self.facts
        )
        self.target_code: int = self.power_on_code

    # ---- dispatch ----

    def process_analog_dispatch(self, from_node: ShNode, dispatch: AnalogDispatch) -> None:
        """from_node is who put the message on the wire (the transport
        header's source); the dispatch's FromHandle is who the sender claims
        to be in the command tree. The two must agree before anything else
        is looked at."""
        if dispatch.FromHandle != from_node.handle:
            self.send_warning(
                "bad_sender",
                f"{from_node.name} (handle {from_node.handle}) sent a dispatch claiming "
                f"FromHandle {dispatch.FromHandle}. Ignoring!",
            )
            return
        if dispatch.ToHandle != self.node.handle:
            self.log(f"Ignoring dispatch {dispatch} - ToHandle is not {self.node.handle}!")
            self._send_to(
                from_node,
                command_reply.nack(
                    self.node.handle, dispatch.FromHandle, dispatch.TriggerId,
                    ScadaCmdRefusalReason.NotMyBoss,
                ),
            )
            return
        if dispatch.AboutName != self.node.name:
            self.log(f"Ignoring dispatch {dispatch} -- expect AboutName to be about me")
        if dispatch.Value not in range(VOLTS_TIMES_TEN_MAX + 1):
            self.log(
                f"Refusing dispatch {dispatch} - value out of range. "
                f"Should be 0-{VOLTS_TIMES_TEN_MAX}"
            )
            self._send_to(
                from_node,
                command_reply.nack(
                    self.node.handle, dispatch.FromHandle, dispatch.TriggerId,
                    ScadaCmdRefusalReason.OutOfRange,
                ),
            )
            return
        self._send_to(
            from_node,
            command_reply.ack(self.node.handle, dispatch.FromHandle, dispatch.TriggerId),
        )
        self.target_code = code_from_volts_times_ten(dispatch.Value, self.facts)
        self.log(
            f"Dispatch from {dispatch.FromHandle}: volts x10 {dispatch.Value} "
            f"-> code {self.target_code}"
        )
        self.wake.set()

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        payload = message.Payload
        if isinstance(payload, AnalogDispatch):
            from_node = self.layout.node(message.Header.Src, None)
            if from_node is None:
                self.log(f"Ignoring {payload.TypeName} from {message.Header.Src} - not in layout")
                return Ok(False)
            try:
                self.process_analog_dispatch(from_node, payload)
            except Exception as e:
                self.log(f"Trouble with process_analog_dispatch: {e}")
            return Ok(True)
        if isinstance(payload, I2cResult):
            future = self.pending_results.pop(payload.TriggerId, None)
            if future is not None and not future.done():
                future.set_result(payload)
            return Ok(True)
        self.log(f"Got unexpected {payload.TypeName} from {message.Header.Src}")
        return Ok(True)

    # ---- glitch throttling (once per failure streak) ----

    def send_warning_once(self, key: str, summary: str, details: str) -> None:
        if key in self.active_warning_keys:
            return
        self.active_warning_keys.add(key)
        self.send_warning(summary=summary, details=details)

    def clear_warning(self, key: str) -> None:
        self.active_warning_keys.discard(key)

    # ---- bus-op plumbing (the reader's round-trip pattern) ----

    async def bus_op(
        self, payload: I2cWriteByte | I2cWriteReg | I2cReadBytes
    ) -> I2cResult | None:
        """Send one op to the bus actor and await its I2cResult (None on
        timeout)."""
        future: "asyncio.Future[I2cResult]" = (
            asyncio.get_running_loop().create_future()
        )
        self.pending_results[payload.TriggerId] = future
        self._send_to(self.bus_node, payload)
        try:
            return await asyncio.wait_for(future, timeout=self.bus_op_timeout_s)
        except asyncio.TimeoutError:
            self.pending_results.pop(payload.TriggerId, None)
            return None

    async def muxed_op(
        self, payload: I2cWriteReg | I2cReadBytes
    ) -> I2cResult | None:
        """Select this DAC's mux channel (when muxed), then run the op."""
        if self.mux_address is not None:
            select = await self.bus_op(
                I2cWriteByte(
                    Bus=self.bus_node.name,
                    I2cAddress=self.mux_address,
                    Value=1 << self.mux_channel,
                    TriggerId=str(uuid.uuid4()),
                )
            )
            if select is None or not select.Success:
                return select
        return await self.bus_op(payload)

    # ---- the write paths ----

    async def write_register(
        self, register: int, first: int, second: int
    ) -> tuple[bool, str]:
        """One two-byte write to a register of this DAC, `first` then
        `second` on the wire. (ok, detail)."""
        result = await self.muxed_op(
            I2cWriteReg(
                Bus=self.bus_node.name,
                Address=I2cRegAddress(
                    I2cAddress=self.dac_address, RegisterIndex=register
                ),
                NumBytes=2,
                Value=(first << 8) | second,
                TriggerId=str(uuid.uuid4()),
            )
        )
        if result is None:
            return False, "bus op timeout"
        if not result.Success:
            return False, result.Error or "unknown bus error"
        return True, ""

    def data_bits(self) -> tuple[int, int]:
        return (
            mcp4728.VREF_BIT[mcp4728.POWER_ON_VREF],
            mcp4728.gain_bit(mcp4728.POWER_ON_GAIN),
        )

    async def write_code(self, code: int, command_base: int) -> tuple[bool, str]:
        """MCP4728: one write of `code` to this channel in the given command
        family. (ok, detail)."""
        vref, gain = self.data_bits()
        hi, lo = mcp4728.encode_data(code, vref, gain)
        return await self.write_register(
            mcp4728.command(command_base, self.channel), hi, lo
        )

    async def write_output(self, code: int) -> tuple[bool, str]:
        """GP8403: one write of `code` to this channel's output register.
        (ok, detail)."""
        first, second = gp8403.word_bytes(gp8403.encode_word(code))
        return await self.write_register(
            gp8403.OUTPUT_REG[self.channel], first, second
        )

    async def write_target(self, code: int) -> tuple[bool, str]:
        """The chip's routine level write: the one that never touches a
        stored power-on value."""
        if self.dac_type == I2cDacType.Mcp4728:
            return await self.write_code(code, mcp4728.MULTI_WRITE_BASE)
        return await self.write_output(code)

    async def assert_target(self) -> None:
        """Write the target level and report it; one Glitch per failure
        streak, retried every heartbeat."""
        code = self.target_code
        value = volts_times_ten_from_code(code, self.facts)
        ok, detail = await self.write_target(code)
        key = "i2c-dac-write-failed"
        if not ok:
            self.send_warning_once(
                key, key, f"{self.name}: volts x10 {value} (code {code}): {detail}"
            )
            return
        self.clear_warning(key)
        self._send_to(
            self.primary_scada,
            SingleReading(
                ChannelName=self.config.ChannelName,
                Value=value,
                ScadaReadTimeUnixMs=int(time.time() * 1000),
            ),
        )

    # ---- the chip's one-time boot step ----

    async def prepare_chip(self) -> bool:
        """MCP4728: verify (and reprogram) the stored power-on level.
        GP8403: set the 0-10 V output range, which the chip does not keep
        across a power-up."""
        if self.dac_type == I2cDacType.Mcp4728:
            return await self.verify_eeprom()
        return await self.set_range()

    async def set_range(self) -> bool:
        ok, detail = await self.write_register(
            gp8403.RANGE_REG, *gp8403.word_bytes(gp8403.RANGE_10V)
        )
        key = "i2c-dac-range-set-failed"
        if not ok:
            self.send_warning_once(key, key, f"{self.name}: {detail}")
            return False
        self.clear_warning(key)
        self.log(f"{self.name}: output range set to 0-10 V")
        return True

    async def read_eeprom_mismatch(self) -> tuple[bool | None, str]:
        """Whether the channel's EEPROM differs from the ops word's power-on
        level (and the driver's reference and gain), or (None, detail) when
        the read itself failed."""
        result = await self.muxed_op(
            I2cReadBytes(
                Bus=self.bus_node.name,
                I2cAddress=self.dac_address,
                NumBytes=mcp4728.READ_LEN,
                TriggerId=str(uuid.uuid4()),
            )
        )
        if result is None:
            return None, "bus op timeout"
        if not result.Success or result.Bytes is None:
            return None, result.Error or "unknown bus error"
        vref, gain = self.data_bits()
        hi, lo = mcp4728.eeprom_data(result.Bytes, self.channel)
        expected = (self.power_on_code, vref, gain)
        read = mcp4728.decode_data(hi, lo)
        if read == expected:
            return False, ""
        return True, f"EEPROM (code, vref, gain) read {read}, ops {expected}"

    async def verify_eeprom(self) -> bool:
        """Read -> compare to the ops power-on level -> reprogram a mismatch
        (Single Write — the one EEPROM-touching path) -> re-verify. A chip
        that stores no power-on value has nothing to verify."""
        if not self.facts.supports_power_on_store:
            return True
        mismatch, mismatch_detail = await self.read_eeprom_mismatch()
        if mismatch is None:
            self.send_warning_once(
                "i2c-dac-eeprom-read-failed",
                "i2c-dac-eeprom-read-failed",
                f"{self.name}: {mismatch_detail}",
            )
            return False
        self.clear_warning("i2c-dac-eeprom-read-failed")
        if not mismatch:
            self.log(f"{self.name}: EEPROM verified against the ops power-on level")
            return True
        await self.write_code(self.power_on_code, mcp4728.SINGLE_WRITE_BASE)
        # let the chip's EEPROM write cycle complete before the next
        # command or the re-read sees stale data
        await asyncio.sleep(mcp4728.EEPROM_WRITE_TIME_S + 0.01)
        still_mismatch, detail = await self.read_eeprom_mismatch()
        if still_mismatch is False:
            self.send_warning(
                summary="i2c-dac-eeprom-reprogrammed",
                details=(
                    f"{self.name}: channel {self.config.DacChannel.value} "
                    f"{mismatch_detail}; reprogrammed and re-verified"
                ),
            )
            return True
        self.send_warning(
            summary="i2c-dac-eeprom-verify-failed",
            details=(
                f"{self.name}: channel {self.config.DacChannel.value} mismatched; "
                f"after reprogram still bad ({detail})"
            ),
        )
        return False

    # ---- lifecycle ----

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.HEARTBEAT_S * 2)]

    def start(self) -> None:
        self.services.add_task(
            asyncio.create_task(self.main_loop(), name=f"{self.name}-main")
        )
        self._send_to(self.primary_scada, ActuatorsReady())

    async def main_loop(self) -> None:
        """Watchdog pat + level enforcement each pass: the chip's boot step
        (retried until it completes once — the bus refuses ops until its
        init guard finishes), then the target write. A dispatch wakes the
        loop early, so writes serialize in this one task."""
        while not self.stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            self.wake.clear()
            if not self.chip_ready:
                self.chip_ready = await self.prepare_chip()
            await self.assert_target()
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=self.HEARTBEAT_S)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self.stop_requested = True
        self.wake.set()

    async def join(self) -> None: ...
