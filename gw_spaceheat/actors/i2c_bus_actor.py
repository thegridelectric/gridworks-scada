import time
from typing import Any, Optional, Sequence
import asyncio

from gwproto.message import Message
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from result import Ok, Err, Result

from actors.sh_node_actor import ShNodeActor
from scada_app_interface import ScadaAppInterface

from gwsproto.named_types import I2cWriteBit, I2cReadBit, I2cResult
from gwsproto.enums import LogLevel
from gwsproto.named_types import Glitch



class I2cBusActor(ShNodeActor):
    """
    Exclusive serialized executor for a single named I2C bus.

    All I2C-backed components must route bus operations through this actor.
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

        if isinstance(payload, I2cWriteBit):
            return self._handle_write_bit(payload)

        if isinstance(payload, I2cReadBit):
            return self._handle_read_bit(payload)

        return Err(
            ValueError(
                f"I2cBusActor {self.name} received unexpected payload {type(payload)}"
            )
        )


    def _handle_write_bit(self, cmd: I2cWriteBit) -> Result[bool, BaseException]:
        now_ms = int(time.time() * 1000)

        try:
            if self.is_simulated or self.i2c is None:
                success = True
                error = None
            else:
                current = self.i2c.read_byte_data(cmd.I2cAddress, cmd.Register)
                if cmd.Value == 1:
                    new = current | (1 << cmd.BitIndex)
                else:
                    new = current & ~(1 << cmd.BitIndex)
                self.i2c.write_byte_data(cmd.I2cAddress, cmd.Register, new)
                success = True
                error = None

        except Exception as e:
            success = False
            error = str(e)

        self._send_to(
            self.primary_scada,
            I2cResult(
                Bus=cmd.Bus,
                TriggerId=cmd.TriggerId,
                Success=success,
                Operation="write.bit",
                I2cAddress=cmd.I2cAddress,
                Register=cmd.Register,
                BitIndex=cmd.BitIndex,
                Value=cmd.Value if success else None,
                Error=error,
                UnixTimeMs=now_ms,
            ),
        )

        return Ok(True)

    def _handle_read_bit(self, cmd: I2cReadBit) -> Result[bool, BaseException]:
        now_ms = int(time.time() * 1000)

        try:
            if self.is_simulated or self.i2c is None:
                value = 0
                success = True
                error = None
            else:
                current = self.i2c.read_byte_data(cmd.I2cAddress, cmd.Register)
                value = (current >> cmd.BitIndex) & 0x01
                success = True
                error = None

        except Exception as e:
            success = False
            value = None
            error = str(e)

        self._send_to(
            self.primary_scada,
            I2cResult(
                Bus=cmd.Bus,
                TriggerId=cmd.TriggerId,
                Success=success,
                Operation="read.bit",
                I2cAddress=cmd.I2cAddress,
                Register=cmd.Register,
                BitIndex=cmd.BitIndex,
                Value=value,
                Error=error,
                UnixTimeMs=now_ms,
            ),
        )

        return Ok(True)

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
