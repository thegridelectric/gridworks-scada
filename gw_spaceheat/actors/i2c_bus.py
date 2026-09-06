import asyncio
import time
from typing import Any, Literal, Optional, Sequence

from gwproto.message import Message
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from pydantic import BaseModel
from result import Ok, Err, Result

from actors.sh_node_actor import ShNodeActor
from drivers import tca9555
from drivers.sim_i2c import SimI2c
from scada_app_interface import ScadaAppInterface

from gwsproto.data_classes.components import I2cRelayComponent
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import I2cOperation, LogLevel
from gwsproto.property_format import NonNegativeInt
from gwsproto.named_types import (
    Glitch,
    I2cReadBit,
    I2cReadBytes,
    I2cReadReg,
    I2cResult,
    I2cWriteBit,
    I2cWriteByte,
    I2cWriteReg,
    ScadaDeviceTypeGt,
)


class ExpanderReinitialized(BaseModel):
    """Process-internal notice from the bus actor to the i2c relay actors:
    the expander at I2cAddress lost and regained its configuration (the
    OPS-452 reset, just repaired), so re-assert your target NOW rather than
    at the next verify pass — 0x21 carries the critical cooling actuators.
    Never crosses the broker: an intra-app signal (the
    PatInternalWatchdogMessage family), not a sema word — the TypeName
    exists only to satisfy the message envelope."""

    I2cAddress: NonNegativeInt
    TypeName: Literal["expander.reinitialized"] = "expander.reinitialized"


class I2cBus(ShNodeActor):
    """
    Exclusive serialized executor for a single named I2C bus.

    All I2C-backed components must route bus operations through this actor;
    each `I2cResult` returns to the requesting node (`Header.Src`).

    Owns the OPS-452 expander guard: adopt-or-init at boot (ops error
    "initializing" until it completes) and a config-register reset check
    each heartbeat, with clear-then-configure repair.

    2-byte register operations are big-endian (register devices like the
    ADS1115 present their 16-bit registers high byte first), NOT SMBus
    little-endian word order — hence block ops, never `read_word_data`.
    """

    BUS_LOOP_S = 60

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)

        self.bus_name = self.node.name

        self._expander_addresses: tuple[int, ...] = tuple(
            expander.I2cAddress
            for record in self.layout.device_types.values()
            if isinstance(record, ScadaDeviceTypeGt)
            for expander in record.Expanders
        )
        self._guard_pending = False

        # The relays to poke for immediate re-assert after a reset repair.
        # Each filters by its own expander address.
        self._i2c_relay_nodes = [
            n
            for n in self.layout.nodes.values()
            if isinstance(n.component, I2cRelayComponent)
        ]

        self.i2c: Optional[Any] = None
        self._stop_requested = False

        # Backend selection happens exactly once, here, from the layout:
        # the board record's DeviceType says whether the silicon is real
        # (Gw108RevB) or simulated (SimGw108). Never from a runtime flag.
        board = self.layout.scada_board()
        if board.simulated:
            record = board.device_type
            self.i2c = SimI2c(
                expander_addresses=self._expander_addresses,
                mux_address=record.Muxes[0].I2cAddress if record.Muxes else None,
                dac_address=record.Dacs[0].I2cAddress if record.Dacs else None,
                dac_mux_channels=tuple(
                    d.MuxChannel for d in record.Dacs if d.MuxChannel is not None
                ),
                adc_addresses=tuple(a.I2cAddress for a in record.ThermistorAdcs),
            )
        else:
            try:
                import smbus2
                self.i2c = smbus2.SMBus(1)
            except Exception as e:
                self.i2c = None
                self._send_glitch(
                    "i2c-bus-init-failed", str(e), LogLevel.Critical
                )

    def _send_glitch(self, summary: str, details: str, level: LogLevel) -> None:
        self._send_to(
            self.ltn,
            Glitch(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                Node=self.name,
                Type=level,
                Summary=summary,
                Details=details,
            ),
        )

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        payload = message.Payload

        reply_to = self.layout.node(message.Header.Src)
        if reply_to is None:
            return Err(
                ValueError(
                    f"I2cBus {self.name} received {type(payload).__name__} from "
                    f"unknown node {message.Header.Src}"
                )
            )

        if isinstance(payload, I2cWriteBit):
            return self._handle_write_bit(payload, reply_to)

        if isinstance(payload, I2cReadBit):
            return self._handle_read_bit(payload, reply_to)

        if isinstance(payload, I2cWriteReg):
            return self._handle_write_reg(payload, reply_to)

        if isinstance(payload, I2cReadReg):
            return self._handle_read_reg(payload, reply_to)

        if isinstance(payload, I2cWriteByte):
            return self._handle_write_byte(payload, reply_to)

        if isinstance(payload, I2cReadBytes):
            return self._handle_read_bytes(payload, reply_to)

        return Err(
            ValueError(
                f"I2cBus {self.name} received unexpected payload {type(payload)}"
            )
        )

    def _reply(
        self,
        reply_to: ShNode,
        bus: str,
        trigger_id: str,
        operation: I2cOperation,
        value: int | None,
        error: str | None,
        bytes_: list[int] | None = None,
    ) -> Result[bool, BaseException]:
        self._send_to(
            reply_to,
            I2cResult(
                Bus=bus,
                Operation=operation,
                Value=value if error is None else None,
                Bytes=bytes_ if error is None else None,
                Success=error is None,
                Error=error,
                UnixTimeMs=int(time.time() * 1000),
                TriggerId=trigger_id,
            ),
        )
        return Ok(True)

    def _op_error(self, bus: str) -> str | None:
        if bus != self.bus_name:
            return f"bus {bus} routed to bus actor {self.bus_name}"
        if self.i2c is None:
            return "no i2c backend"
        if self._guard_pending:
            return "bus initializing: expander guard has not completed"
        return None

    def _handle_write_bit(
        self, cmd: I2cWriteBit, reply_to: ShNode
    ) -> Result[bool, BaseException]:
        value: int | None = None
        error = self._op_error(cmd.Bus)
        if error is None:
            a = cmd.Address
            try:
                current = self.i2c.read_byte_data(a.I2cAddress, a.RegisterIndex)
                if cmd.Value == 1:
                    new = current | (1 << a.BitIndex)
                else:
                    new = current & ~(1 << a.BitIndex)
                self.i2c.write_byte_data(a.I2cAddress, a.RegisterIndex, new)
                value = cmd.Value
            except Exception as e:
                error = str(e)
        return self._reply(
            reply_to, cmd.Bus, cmd.TriggerId, I2cOperation.WriteBit, value, error
        )

    def _handle_read_bit(
        self, cmd: I2cReadBit, reply_to: ShNode
    ) -> Result[bool, BaseException]:
        value: int | None = None
        error = self._op_error(cmd.Bus)
        if error is None:
            a = cmd.Address
            try:
                current = self.i2c.read_byte_data(a.I2cAddress, a.RegisterIndex)
                value = (current >> a.BitIndex) & 0x01
            except Exception as e:
                error = str(e)
        return self._reply(
            reply_to, cmd.Bus, cmd.TriggerId, I2cOperation.ReadBit, value, error
        )

    def _handle_write_reg(
        self, cmd: I2cWriteReg, reply_to: ShNode
    ) -> Result[bool, BaseException]:
        value: int | None = None
        error = self._op_error(cmd.Bus)
        if error is None:
            a = cmd.Address
            try:
                if cmd.NumBytes == 1:
                    self.i2c.write_byte_data(a.I2cAddress, a.RegisterIndex, cmd.Value)
                    value = cmd.Value
                else:
                    self.i2c.write_i2c_block_data(
                        a.I2cAddress,
                        a.RegisterIndex,
                        [(cmd.Value >> 8) & 0xFF, cmd.Value & 0xFF],
                    )
                    value = cmd.Value
            except Exception as e:
                error = str(e)
        return self._reply(
            reply_to, cmd.Bus, cmd.TriggerId, I2cOperation.WriteReg, value, error
        )

    def _handle_read_reg(
        self, cmd: I2cReadReg, reply_to: ShNode
    ) -> Result[bool, BaseException]:
        value: int | None = None
        error = self._op_error(cmd.Bus)
        if error is None:
            a = cmd.Address
            try:
                if cmd.NumBytes == 1:
                    value = self.i2c.read_byte_data(a.I2cAddress, a.RegisterIndex)
                else:
                    b = self.i2c.read_i2c_block_data(a.I2cAddress, a.RegisterIndex, 2)
                    value = (b[0] << 8) | b[1]
            except Exception as e:
                error = str(e)
        return self._reply(
            reply_to, cmd.Bus, cmd.TriggerId, I2cOperation.ReadReg, value, error
        )

    def _handle_write_byte(
        self, cmd: I2cWriteByte, reply_to: ShNode
    ) -> Result[bool, BaseException]:
        value: int | None = None
        error = self._op_error(cmd.Bus)
        if error is None:
            try:
                self.i2c.write_byte(cmd.I2cAddress, cmd.Value)
                value = cmd.Value
            except Exception as e:
                error = str(e)
        return self._reply(
            reply_to, cmd.Bus, cmd.TriggerId, I2cOperation.WriteByte, value, error
        )

    def _receive_bytes(self, address: int, num_bytes: int) -> list[int]:
        """Bare sequential receive — no register pointer. Two genuine
        implementations: the sim backend reads its register model directly;
        smbus2 needs an i2c_rdwr read message (read_i2c_block_data would
        send a command byte first, which is a different wire protocol)."""
        if isinstance(self.i2c, SimI2c):
            return self.i2c.read_bytes(address, num_bytes)
        import smbus2
        msg = smbus2.i2c_msg.read(address, num_bytes)
        self.i2c.i2c_rdwr(msg)
        return list(msg)

    def _handle_read_bytes(
        self, cmd: I2cReadBytes, reply_to: ShNode
    ) -> Result[bool, BaseException]:
        bytes_: list[int] | None = None
        error = self._op_error(cmd.Bus)
        if error is None:
            try:
                bytes_ = self._receive_bytes(cmd.I2cAddress, cmd.NumBytes)
            except Exception as e:
                error = str(e)
        return self._reply(
            reply_to,
            cmd.Bus,
            cmd.TriggerId,
            I2cOperation.ReadBytes,
            None,
            error,
            bytes_=bytes_,
        )

    # ---- the OPS-452 expander guard ----

    def _read_config_regs(self, address: int) -> tuple[int, int]:
        return (
            self.i2c.read_byte_data(address, tca9555.CONFIG_PORT_0),
            self.i2c.read_byte_data(address, tca9555.CONFIG_PORT_1),
        )

    def _clear_then_configure(self, address: int) -> None:
        """The mandatory init order (the 07-18 POR experiment): POR outputs
        are all-1s, so configuring before clearing would drive every relay
        ON."""
        for register in (
            tca9555.OUTPUT_PORT_0,
            tca9555.OUTPUT_PORT_1,
            tca9555.CONFIG_PORT_0,
            tca9555.CONFIG_PORT_1,
        ):
            self.i2c.write_byte_data(address, register, 0x00)

    def _register_snapshot(self) -> str:
        """Full forensic dump of every expander — logged with a reset
        Critical so the evidence lives in the glitch, not in ad-hoc reads."""
        parts = []
        for address in self._expander_addresses:
            try:
                parts.append(
                    f"0x{address:02x}["
                    f"in0={self.i2c.read_byte_data(address, tca9555.INPUT_PORT_0):08b}"
                    f" in1={self.i2c.read_byte_data(address, tca9555.INPUT_PORT_1):08b}"
                    f" out2={self.i2c.read_byte_data(address, tca9555.OUTPUT_PORT_0):08b}"
                    f" out3={self.i2c.read_byte_data(address, tca9555.OUTPUT_PORT_1):08b}"
                    f" cfg6={self.i2c.read_byte_data(address, tca9555.CONFIG_PORT_0):08b}"
                    f" cfg7={self.i2c.read_byte_data(address, tca9555.CONFIG_PORT_1):08b}]"
                )
            except Exception as e:  # noqa: PERF203
                parts.append(f"0x{address:02x}[read failed: {e}]")
        return " ".join(parts)

    async def _init_expanders(self) -> None:
        """Adopt-or-init at boot: config regs already all-outputs is a warm
        takeover (a running hack or a restart left the outputs driving —
        leave them, so relay pin-adoption inherits latched holds); anything
        else is POR or damage — clear-then-configure to safe-off."""
        try:
            for address in self._expander_addresses:
                try:
                    cfg0, cfg1 = self._read_config_regs(address)
                except Exception as e:
                    self._send_glitch(
                        "i2c-expander-init-failed",
                        f"0x{address:02x}: config-register read failed: {e}",
                        LogLevel.Critical,
                    )
                    continue
                if cfg0 == 0 and cfg1 == 0:
                    self.log(
                        f"expander 0x{address:02x}: already configured — "
                        "warm takeover, outputs left driving"
                    )
                    continue
                try:
                    self._clear_then_configure(address)
                    self._send_glitch(
                        "i2c-expander-initialized",
                        f"0x{address:02x} config regs were "
                        f"0x{cfg0:02x}/0x{cfg1:02x} (POR or damage); cleared "
                        "to safe-off and configured as outputs",
                        LogLevel.Warning,
                    )
                except Exception as e:
                    self._send_glitch(
                        "i2c-expander-init-failed",
                        f"0x{address:02x}: clear-then-configure failed: {e}",
                        LogLevel.Critical,
                    )
        finally:
            self._guard_pending = False

    async def _check_expanders(self) -> None:
        """The heartbeat reset guard: any nonzero config bit means our
        outputs are not driving. Confirm with a second read 0.5 s later so a
        single garbled read cannot fire a false Critical or a repair."""
        for address in self._expander_addresses:
            try:
                cfg0, cfg1 = self._read_config_regs(address)
            except Exception as e:
                self._send_glitch(
                    "i2c-expander-check-failed",
                    f"0x{address:02x}: config-register read failed: {e}",
                    LogLevel.Warning,
                )
                continue
            if cfg0 == 0 and cfg1 == 0:
                continue
            await asyncio.sleep(0.5)
            try:
                cfg0, cfg1 = self._read_config_regs(address)
            except Exception as e:
                self._send_glitch(
                    "i2c-expander-check-failed",
                    f"0x{address:02x}: confirm re-read failed: {e}",
                    LogLevel.Warning,
                )
                continue
            if cfg0 == 0 and cfg1 == 0:
                self.log(
                    f"expander 0x{address:02x}: config-register read glitch "
                    "— nonzero once, clean on confirm re-read (not a reset)"
                )
                continue
            self._send_glitch(
                "i2c-expander-reset",
                f"0x{address:02x} config regs 0x{cfg0:02x}/0x{cfg1:02x} — "
                "pins floating (the OPS-452 signature). Re-initializing; "
                "relays re-assert on their verify loops. Registers at "
                f"detection: {self._register_snapshot()}",
                LogLevel.Critical,
            )
            try:
                self._clear_then_configure(address)
                self.log(f"expander 0x{address:02x} re-initialized")
            except Exception as e:
                self._send_glitch(
                    "i2c-expander-reinit-failed",
                    f"0x{address:02x}: {e}",
                    LogLevel.Critical,
                )
                continue
            for node in self._i2c_relay_nodes:
                self._send_to(node, ExpanderReinitialized(I2cAddress=address))

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.BUS_LOOP_S * 2)]

    def start(self) -> None:
        if self._expander_addresses and self.i2c is not None:
            self._guard_pending = True
            self.services.add_task(
                asyncio.create_task(
                    self._init_expanders(), name="i2c-bus-init-guard"
                )
            )
        self.services.add_task(
            asyncio.create_task(self._heartbeat(), name="i2c-bus-heartbeat")
        )

    async def _heartbeat(self) -> None:
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            if (
                not self._guard_pending
                and self.i2c is not None
                and self._expander_addresses
            ):
                await self._check_expanders()
            await asyncio.sleep(self.BUS_LOOP_S)

    def stop(self) -> None:
        self._stop_requested = True

    async def join(self) -> None:
        ...
