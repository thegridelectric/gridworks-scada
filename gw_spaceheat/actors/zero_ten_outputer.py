"""One 0-10V output as an actuator: a leaf of the command tree that takes
AnalogDispatch from its boss and drives a level."""

import asyncio
import time
import uuid
from typing import Sequence

from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto.message import Message
from result import Ok, Result

from actors.sh_node_actor import ShNodeActor
from drivers import mcp4728
from scada_app_interface import ScadaAppInterface

from gwsproto.data_classes.components import I2cDacOutputComponent
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import ActorClass, I2cDacChannel, I2cDacVref
from gwsproto.named_types import (
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
# unit the DFR multiplexer drives and the VoltsTimesTen channel reports.
VOLTS_TIMES_TEN_MAX = 100
MCP4728_CODES = 4096
MCP4728_INTERNAL_VREF_V = 2.048
# The gw108 output stage amplifies the chip's output 5x (2.048 V full scale
# at gain 1 -> 10.24 V at the terminal). Missing word: the board record's
# i2c.dac.capability carries no output scale; this constant retires when it
# does, resolved through the component's board record like the address.
GW108_OUTPUT_GAIN = 5


def output_full_scale_volts(config: DacOutputConfig) -> float:
    """Terminal volts at code 4096 for this channel's reference and gain."""
    return MCP4728_INTERNAL_VREF_V * config.PowerOnGain * GW108_OUTPUT_GAIN


def code_from_volts_times_ten(value: int, config: DacOutputConfig) -> int:
    """The 12-bit code that drives `value` (volts times ten) at the terminal."""
    return round(value / 10 / output_full_scale_volts(config) * MCP4728_CODES)


def volts_times_ten_from_code(code: int, config: DacOutputConfig) -> int:
    return round(code / MCP4728_CODES * output_full_scale_volts(config) * 10)


class ZeroTenOutputer(ShNodeActor):
    """
    The component selects the mechanism, as with Relay:

    - I2cDacOutputComponent (Nolan): one channel of a board DAC, resolved
      from the component's board record (DacName -> address, mux) and driven
      through the I2cBus single owner. Boot EEPROM verify against the
      declared power-on defaults (Single Write only on a mismatch: the one
      EEPROM-touching path), then Multi-Write of the target level — the
      power-on level until the first dispatch, the last commanded level
      after — re-asserted every heartbeat and on every dispatch. A
      successful write reports the level on the output's channel.
    - No component (House0): the DFR multiplexer node owns the DFR board
      and its per-output configs; this node forwards the dispatch to it.
      Missing word: a per-output DFR component (the DFR analog of
      i2c.dac.output.component.gt); this branch retires when it lands.
    """

    HEARTBEAT_S = 60

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self.dac: I2cDacOutputComponent | None = None
        self.dfr_multiplexer: ShNode | None = None
        self.bus_op_timeout_s = 1.0
        self.pending_results: dict[str, "asyncio.Future[I2cResult]"] = {}
        self.stop_requested = False
        self.eeprom_verified = False
        self.active_warning_keys: set[str] = set()
        self.wake = asyncio.Event()

        component = self.node.component
        if isinstance(component, I2cDacOutputComponent):
            self.dac = component
            self.resolve_dac(component)
        elif component is None:
            multiplexer = self.layout.node(H0N.zero_ten_out_multiplexer)
            if multiplexer is None:
                raise ValueError(
                    f"{self.name}: no component and no "
                    f"{H0N.zero_ten_out_multiplexer} node to forward to"
                )
            self.dfr_multiplexer = multiplexer
        else:
            raise ValueError(
                f"{self.name} expected I2cDacOutputComponent or no component, "
                f"got {type(component)}"
            )

    def resolve_dac(self, component: I2cDacOutputComponent) -> None:
        """DacName resolved against THIS component's board record — the
        record's DAC list holds the physical address and mux position; the
        layout never restates it."""
        config = component.gt.ConfigList[0]
        if config.ActorName != self.name:
            raise ValueError(
                f"{self.name}: component config names actor {config.ActorName}"
            )
        if config.PowerOnVref != I2cDacVref.Internal:
            raise ValueError(
                f"{self.name}: PowerOnVref {config.PowerOnVref} unsupported — "
                "the Vdd reference has no declared supply voltage to scale by"
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
        # The code the heartbeat drives: the declared power-on code until
        # the first dispatch (exactly, not rounded through volts x10), the
        # last commanded level after.
        self.target_code: int = config.PowerOnRawValue

    # ---- dispatch ----

    def process_analog_dispatch(self, dispatch: AnalogDispatch) -> None:
        if not self.layout.node_by_handle(dispatch.FromHandle):
            self.log(f"Ignoring dispatch from handle {dispatch.FromHandle} - not in layout!!")
            return
        if dispatch.ToHandle != self.node.handle:
            self.log(f"Ignoring dispatch {dispatch} - ToHandle is not {self.node.handle}!")
            return
        if dispatch.AboutName != self.node.name:
            self.log(f"Ignoring dispatch {dispatch} -- expect AboutName to be about me")
        if dispatch.Value not in range(VOLTS_TIMES_TEN_MAX + 1):
            self.log(
                f"Ignoring dispatch {dispatch} - value out of range. "
                f"Should be 0-{VOLTS_TIMES_TEN_MAX}"
            )
            return
        if self.dac is not None:
            self.target_code = code_from_volts_times_ten(dispatch.Value, self.config)
            self.wake.set()
            return
        assert self.dfr_multiplexer is not None
        self._send_to(
            self.dfr_multiplexer,
            AnalogDispatch(
                FromHandle=self.node.handle,
                ToHandle=self.dfr_multiplexer.handle,
                AboutName=self.name,
                Value=dispatch.Value,
                TriggerId=dispatch.TriggerId,
                UnixTimeMs=int(time.time() * 1000),
            ),
        )

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        payload = message.Payload
        if isinstance(payload, AnalogDispatch):
            try:
                self.process_analog_dispatch(payload)
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

    def data_bits(self) -> tuple[int, int]:
        return (
            mcp4728.VREF_BIT[self.config.PowerOnVref.value],
            mcp4728.gain_bit(self.config.PowerOnGain),
        )

    async def write_code(self, code: int, command_base: int) -> tuple[bool, str]:
        """One write of `code` to this channel in the given command family.
        (ok, detail)."""
        vref, gain = self.data_bits()
        hi, lo = mcp4728.encode_data(code, vref, gain)
        result = await self.muxed_op(
            I2cWriteReg(
                Bus=self.bus_node.name,
                Address=I2cRegAddress(
                    I2cAddress=self.dac_address,
                    RegisterIndex=mcp4728.command(command_base, self.channel),
                ),
                NumBytes=2,
                Value=(hi << 8) | lo,
                TriggerId=str(uuid.uuid4()),
            )
        )
        if result is None:
            return False, "bus op timeout"
        if not result.Success:
            return False, result.Error or "unknown bus error"
        return True, ""

    async def assert_target(self) -> None:
        """Multi-Write the target level (input register only) and report it;
        one Glitch per failure streak, retried every heartbeat."""
        code = self.target_code
        value = volts_times_ten_from_code(code, self.config)
        ok, detail = await self.write_code(code, mcp4728.MULTI_WRITE_BASE)
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

    # ---- the boot EEPROM verify ----

    async def read_eeprom_mismatch(self) -> tuple[bool | None, str]:
        """Whether the channel's EEPROM differs from the declared PowerOn
        values, or (None, detail) when the read itself failed."""
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
        expected = (self.config.PowerOnRawValue, vref, gain)
        return mcp4728.decode_data(hi, lo) != expected, ""

    async def verify_eeprom(self) -> bool:
        """Read -> compare to the declared PowerOn values -> reprogram a
        mismatch (Single Write — the one EEPROM-touching path) -> re-verify."""
        mismatch, detail = await self.read_eeprom_mismatch()
        if mismatch is None:
            self.send_warning_once(
                "i2c-dac-eeprom-read-failed",
                "i2c-dac-eeprom-read-failed",
                f"{self.name}: {detail}",
            )
            return False
        self.clear_warning("i2c-dac-eeprom-read-failed")
        if not mismatch:
            self.log(f"{self.name}: EEPROM verified against layout PowerOn values")
            return True
        await self.write_code(self.config.PowerOnRawValue, mcp4728.SINGLE_WRITE_BASE)
        # let the chip's EEPROM write cycle complete before the next
        # command or the re-read sees stale data
        await asyncio.sleep(mcp4728.EEPROM_WRITE_TIME_S + 0.01)
        still_mismatch, detail = await self.read_eeprom_mismatch()
        if still_mismatch is False:
            self.send_warning(
                summary="i2c-dac-eeprom-reprogrammed",
                details=(
                    f"{self.name}: channel {self.config.DacChannel.value} EEPROM did "
                    "not match the layout PowerOn values; reprogrammed and re-verified"
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
        if self.dac is None:
            return []
        return [MonitoredName(self.name, self.HEARTBEAT_S * 2)]

    def start(self) -> None:
        if self.dac is None:
            return
        self.services.add_task(
            asyncio.create_task(self.main_loop(), name=f"{self.name}-main")
        )

    async def main_loop(self) -> None:
        """Watchdog pat + level enforcement each pass: EEPROM verify (retried
        until it completes once — the bus refuses ops until its init guard
        finishes), then Multi-Write of the target. A dispatch wakes the loop
        early, so writes serialize in this one task."""
        while not self.stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            self.wake.clear()
            if not self.eeprom_verified:
                self.eeprom_verified = await self.verify_eeprom()
            await self.assert_target()
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=self.HEARTBEAT_S)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self.stop_requested = True
        self.wake.set()

    async def join(self) -> None: ...
