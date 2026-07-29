import asyncio
import time
from typing import Any, Optional, Sequence

from gwproto.message import Message
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from result import Ok, Err, Result

from actors.sh_node_actor import ShNodeActor
from scada_app_interface import ScadaAppInterface

from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import I2cOperation, LogLevel
from gwsproto.named_types import (
    Glitch,
    I2cReadBit,
    I2cReadReg,
    I2cResult,
    I2cWriteBit,
    I2cWriteReg,
)


class I2cBus(ShNodeActor):
    """
    Exclusive serialized executor for a single named I2C bus.

    All I2C-backed components must route bus operations through this actor;
    each `I2cResult` returns to the requesting node (`Header.Src`).

    2-byte register operations are big-endian (register devices like the
    ADS1115 present their 16-bit registers high byte first), NOT SMBus
    little-endian word order — hence block ops, never `read_word_data`.
    """

    BUS_LOOP_S = 60

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)

        self.bus_name = self.node.name
        self.is_simulated = self.settings.is_simulated

        self.i2c: Optional[Any] = None
        self._stop_requested = False

        if not self.is_simulated:
            try:
                import smbus2
                self.i2c = smbus2.SMBus(1)
            except Exception as e:
                self.i2c = None
                self._send_to(
                    self.ltn,
                    Glitch(
                        FromGNodeAlias=self.layout.scada_g_node_alias,
                        Node=self.name,
                        Type=LogLevel.Critical,
                        Summary="i2c-bus-init-failed",
                        Details=str(e),
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
    ) -> Result[bool, BaseException]:
        self._send_to(
            reply_to,
            I2cResult(
                Bus=bus,
                Operation=operation,
                Value=value if error is None else None,
                Success=error is None,
                Error=error,
                UnixTimeMs=int(time.time() * 1000),
                TriggerId=trigger_id,
            ),
        )
        return Ok(True)

    def _wrong_bus_error(self, bus: str) -> str | None:
        if bus != self.bus_name:
            return f"bus {bus} routed to bus actor {self.bus_name}"
        return None

    def _handle_write_bit(
        self, cmd: I2cWriteBit, reply_to: ShNode
    ) -> Result[bool, BaseException]:
        value: int | None = None
        error = self._wrong_bus_error(cmd.Bus)
        if error is None:
            a = cmd.Address
            try:
                if self.is_simulated or self.i2c is None:
                    value = cmd.Value
                else:
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
        error = self._wrong_bus_error(cmd.Bus)
        if error is None:
            a = cmd.Address
            try:
                if self.is_simulated or self.i2c is None:
                    value = 0
                else:
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
        error = self._wrong_bus_error(cmd.Bus)
        if error is None:
            a = cmd.Address
            try:
                if self.is_simulated or self.i2c is None:
                    value = cmd.Value
                elif cmd.NumBytes == 1:
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
        error = self._wrong_bus_error(cmd.Bus)
        if error is None:
            a = cmd.Address
            try:
                if self.is_simulated or self.i2c is None:
                    value = 0
                elif cmd.NumBytes == 1:
                    value = self.i2c.read_byte_data(a.I2cAddress, a.RegisterIndex)
                else:
                    b = self.i2c.read_i2c_block_data(a.I2cAddress, a.RegisterIndex, 2)
                    value = (b[0] << 8) | b[1]
            except Exception as e:
                error = str(e)
        return self._reply(
            reply_to, cmd.Bus, cmd.TriggerId, I2cOperation.ReadReg, value, error
        )

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.BUS_LOOP_S * 2)]

    def start(self) -> None:
        self.services.add_task(
            asyncio.create_task(self._heartbeat(), name="i2c-bus-heartbeat")
        )

    async def _heartbeat(self) -> None:
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            await asyncio.sleep(self.BUS_LOOP_S)

    def stop(self) -> None:
        self._stop_requested = True

    async def join(self) -> None:
        ...
