import asyncio
import uuid
from typing import Sequence

from gwproto.message import Message
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from result import Ok, Err, Result

from actors.sh_node_actor import ShNodeActor
from drivers import mcp4728
from scada_app_interface import ScadaAppInterface

from gwsproto.data_classes.components import I2cDacWriterComponent
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import ActorClass, I2cDacChannel
from gwsproto.named_types import (
    I2cDacChannelConfig,
    I2cReadBytes,
    I2cRegAddress,
    I2cResult,
    I2cWriteByte,
    I2cWriteReg,
)

CHANNEL_INDEX = {
    I2cDacChannel.A: 0,
    I2cDacChannel.B: 1,
    I2cDacChannel.C: 2,
    I2cDacChannel.D: 3,
}


class I2cDacWriter(ShNodeActor):
    """
    Holds the declared output values on one MCP4728 DAC, resolved wholly
    from the layout: the component's DacName finds the board record's DAC
    capability (device address, mux binding), and the ConfigList carries
    the per-channel targets. Every wire operation rides the I2cBus single
    owner — the mux channel select is global bus state, so an out-of-band
    writer would race every other muxed op.

    Routine assertion uses Multi-Write (input register only). Single Write
    would also program the channel's EEPROM on every pass: finite EEPROM
    endurance spent on a 60 s heartbeat, and the provisioned power-on
    default silently replaced by the last commanded value. EEPROM is
    touched only by the boot verify: read, compare against the declared
    PowerOn values, reprogram a mismatch, re-verify.

    The targets are the layout's PowerOn values; there is no runtime
    dispatch surface yet. Restoring one needs a channel binding on
    i2c.dac.channel.config (which about-node or channel a DAC channel
    serves) — a missing sema field, to land with the zone-analog
    capability work.
    """

    HEARTBEAT_S = 60

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)

        component = self.node.component
        if not isinstance(component, I2cDacWriterComponent):
            raise ValueError(
                f"{self.name} expected I2cDacWriterComponent, got {type(component)}"
            )
        self.component: I2cDacWriterComponent = component

        record = component.board_component.device_type
        dac = next(
            d for d in record.Dacs if d.DacName == component.gt.DacName
        )
        self.dac_address: int = dac.I2cAddress
        if dac.MuxName is not None:
            mux = next(m for m in record.Muxes if m.MuxName == dac.MuxName)
            self.mux_address: int | None = mux.I2cAddress
            self.mux_channel: int | None = dac.MuxChannel
        else:
            self.mux_address = None
            self.mux_channel = None

        self.configs: dict[int, I2cDacChannelConfig] = {
            CHANNEL_INDEX[cfg.DacChannel]: cfg
            for cfg in component.gt.ConfigList
        }

        self.is_simulated = self.services.is_simulated
        self.bus_op_timeout_s = 1.0
        self._pending_results: dict[str, "asyncio.Future[I2cResult]"] = {}
        self._stop_requested = False
        self._eeprom_verified = False
        self._active_warning_keys: set[str] = set()

        bus_nodes = [
            n
            for n in self.layout.nodes.values()
            if n.ActorClass == ActorClass.I2cBus
        ]
        self.bus_node: ShNode | None = (
            bus_nodes[0] if len(bus_nodes) == 1 else None
        )
        if self.bus_node is None:
            raise ValueError(
                f"{self.name}: expected exactly one I2cBus node in the "
                f"layout; found {len(bus_nodes)}"
            )

    # ---- glitch throttling (once per failure streak) ----

    def _send_warning_once(self, key: str, summary: str, details: str) -> None:
        if key in self._active_warning_keys:
            return
        self._active_warning_keys.add(key)
        self.send_warning(summary=summary, details=details)

    def _clear_warning(self, key: str) -> None:
        self._active_warning_keys.discard(key)

    # ---- bus-op plumbing (the reader's round-trip pattern) ----

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        payload = message.Payload
        if isinstance(payload, I2cResult):
            future = self._pending_results.pop(payload.TriggerId, None)
            if future is not None and not future.done():
                future.set_result(payload)
            return Ok(True)
        return Err(
            ValueError(f"{self.name} received unexpected payload {type(payload)}")
        )

    async def _bus_op(
        self, payload: I2cWriteByte | I2cWriteReg | I2cReadBytes
    ) -> I2cResult | None:
        """Send one op to the bus actor and await its I2cResult (None on
        timeout)."""
        future: "asyncio.Future[I2cResult]" = (
            asyncio.get_running_loop().create_future()
        )
        self._pending_results[payload.TriggerId] = future
        self._send_to(self.bus_node, payload)
        try:
            return await asyncio.wait_for(future, timeout=self.bus_op_timeout_s)
        except asyncio.TimeoutError:
            self._pending_results.pop(payload.TriggerId, None)
            return None

    async def _muxed_op(
        self, payload: I2cWriteReg | I2cReadBytes
    ) -> I2cResult | None:
        """Select this DAC's mux channel (when muxed), then run the op."""
        if self.mux_address is not None:
            select = await self._bus_op(
                I2cWriteByte(
                    Bus=self.bus_node.name,
                    I2cAddress=self.mux_address,
                    Value=1 << self.mux_channel,
                    TriggerId=str(uuid.uuid4()),
                )
            )
            if select is None or not select.Success:
                return select
        return await self._bus_op(payload)

    # ---- the write paths ----

    def _data_bits(self, cfg: I2cDacChannelConfig) -> tuple[int, int]:
        return (
            mcp4728.VREF_BIT[cfg.PowerOnVref.value],
            mcp4728.gain_bit(cfg.PowerOnGain),
        )

    async def _write_channel(
        self, channel: int, command_base: int
    ) -> tuple[bool, str]:
        """One channel write in the given command family. (ok, detail)."""
        cfg = self.configs[channel]
        vref, gain = self._data_bits(cfg)
        hi, lo = mcp4728.encode_data(cfg.PowerOnRawValue, vref, gain)
        result = await self._muxed_op(
            I2cWriteReg(
                Bus=self.bus_node.name,
                Address=I2cRegAddress(
                    I2cAddress=self.dac_address,
                    RegisterIndex=mcp4728.command(command_base, channel),
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

    async def _assert_targets(self) -> None:
        """Multi-Write every declared channel to its target (input register
        only); one Glitch per failure streak, retried every heartbeat."""
        for channel in sorted(self.configs):
            ok, detail = await self._write_channel(
                channel, mcp4728.MULTI_WRITE_BASE
            )
            key = f"i2c-dac-write-failed-{channel}"
            if ok:
                self._clear_warning(key)
            else:
                self._send_warning_once(
                    key,
                    "i2c-dac-write-failed",
                    f"{self.name}: channel {channel} "
                    f"raw={self.configs[channel].PowerOnRawValue}: {detail}",
                )

    # ---- the boot EEPROM verify ----

    async def _read_eeprom_mismatches(self) -> tuple[list[int] | None, str]:
        """Channels whose EEPROM differs from the declared PowerOn values,
        or (None, detail) when the read itself failed."""
        result = await self._muxed_op(
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
        mismatched = []
        for channel, cfg in self.configs.items():
            vref, gain = self._data_bits(cfg)
            hi, lo = mcp4728.eeprom_data(result.Bytes, channel)
            if mcp4728.decode_data(hi, lo) != (cfg.PowerOnRawValue, vref, gain):
                mismatched.append(channel)
        return mismatched, ""

    async def _verify_eeprom(self) -> bool:
        """Read → compare to the declared PowerOn values → reprogram any
        mismatch (Single Write — the one EEPROM-touching path) → re-verify."""
        mismatched, detail = await self._read_eeprom_mismatches()
        if mismatched is None:
            self._send_warning_once(
                "i2c-dac-eeprom-read-failed",
                "i2c-dac-eeprom-read-failed",
                f"{self.name}: {detail}",
            )
            return False
        self._clear_warning("i2c-dac-eeprom-read-failed")
        if not mismatched:
            self.log(f"{self.name}: EEPROM verified against layout PowerOn values")
            return True
        for channel in mismatched:
            await self._write_channel(channel, mcp4728.SINGLE_WRITE_BASE)
            # let the chip's EEPROM write cycle complete before the next
            # command or the re-read sees stale data
            await asyncio.sleep(mcp4728.EEPROM_WRITE_TIME_S + 0.01)
        still_mismatched, detail = await self._read_eeprom_mismatches()
        if still_mismatched == []:
            self.send_warning(
                summary="i2c-dac-eeprom-reprogrammed",
                details=(
                    f"{self.name}: channels {mismatched} EEPROM did not match "
                    "the layout PowerOn values; reprogrammed and re-verified"
                ),
            )
            return True
        self.send_warning(
            summary="i2c-dac-eeprom-verify-failed",
            details=(
                f"{self.name}: channels {mismatched} mismatched; after "
                f"reprogram still bad: {still_mismatched} ({detail})"
            ),
        )
        return False

    # ---- lifecycle ----

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.HEARTBEAT_S * 2)]

    def start(self) -> None:
        self.services.add_task(
            asyncio.create_task(self._main(), name=f"{self.name}-main")
        )

    async def _main(self) -> None:
        """Watchdog pat + drift enforcement each period: EEPROM verify
        (retried until it completes once — the bus refuses ops until its
        init guard finishes), then Multi-Write assertion of every target."""
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            if not self._eeprom_verified:
                self._eeprom_verified = await self._verify_eeprom()
            await self._assert_targets()
            await asyncio.sleep(self.HEARTBEAT_S)

    def stop(self) -> None:
        self._stop_requested = True

    async def join(self) -> None:
        ...
