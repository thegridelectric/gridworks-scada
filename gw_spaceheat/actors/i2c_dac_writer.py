import asyncio
from typing import Any, Optional, Sequence

from gwproto.message import Message
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from result import Ok, Err, Result

from actors.sh_node_actor import ShNodeActor
from scada_app_interface import ScadaAppInterface

from gwsproto.named_types import AnalogDispatch


class I2cDacWriter(ShNodeActor):
    """
    Drives one MCP4728 DAC channel behind the TCA9548A mux (the gw108
    0-10V outputs) from AnalogDispatch (Value 0-100 = percent of 10 V).

    Containment is the point: every i2c write is wrapped — a failure
    becomes a warning Glitch (`i2c-dac-write-failed`) and the actor keeps
    its last commanded value, re-asserting on the periodic heartbeat, so a
    transient bus fault (a mux write timing out, a supply blip) costs one
    heartbeat period, never a crash.

    Direct smbus2 for now: the mux channel select is a bare-byte write the
    published i2c reg-op vocabulary cannot express, so these ops cannot yet
    ride the I2cBus actor. The mux select is global bus state — while any
    other process drives the DACs (the summer hack), exactly one writer may
    run.
    """

    HEARTBEAT_S = 60

    # gw108 DAC hardware facts (starter-scripts/gw108_test_code.py map):
    # three MCP4728s behind the TCA9548A at 0x70; MCP4728 device address.
    MUX_ADDRESS = 0x70
    DAC_ADDRESS = 0x60
    # Observed calibration: 10 V out at raw 4000, linear (internal vref,
    # gain 1, external amplification stage).
    RAW_PER_PERCENT = 40
    # MCP4728 single-write command: 0b01011_cc_0 (cc = channel index),
    # data hi byte carries VREF=1 (internal), PD=00, Gx=0 (gain 1).
    _SINGLE_WRITE_CMD = 0x58
    _HI_BITS = 0x80

    def __init__(
        self,
        name: str,
        services: ScadaAppInterface,
        *,
        mux_channel: int,
        dac_channel: int,
    ):
        super().__init__(name, services)
        self.is_simulated = self.settings.is_simulated
        self.mux_channel = mux_channel
        self.dac_channel = dac_channel
        self.last_commanded_raw: Optional[int] = None
        self._stop_requested = False

        self.i2c: Optional[Any] = None
        if not self.is_simulated:
            try:
                import smbus2
                self.i2c = smbus2.SMBus(1)
            except Exception as e:
                self.i2c = None
                self.send_warning(
                    summary="i2c-dac-init-failed",
                    details=f"{self.name}: {e}",
                )

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        payload = message.Payload
        if isinstance(payload, AnalogDispatch):
            self.process_analog_dispatch(payload)
            return Ok(True)
        return Err(
            ValueError(f"{self.name} received unexpected payload {type(payload)}")
        )

    def process_analog_dispatch(self, dispatch: AnalogDispatch) -> None:
        if dispatch.ToHandle != self.node.handle:
            self.log(f"Ignoring dispatch {dispatch} - ToHandle is not {self.node.handle}")
            return
        if dispatch.Value not in range(101):
            self.log(f"Ignoring dispatch {dispatch} - Value must be 0-100")
            return
        self.last_commanded_raw = dispatch.Value * self.RAW_PER_PERCENT
        self._write_dac()

    def _write_dac(self) -> bool:
        """Assert last_commanded_raw on the hardware. False (+ one Glitch per
        failure streak) on any i2c fault; the heartbeat retries."""
        if self.last_commanded_raw is None:
            return True
        if self.is_simulated or self.i2c is None:
            return True
        raw = self.last_commanded_raw
        try:
            self.i2c.write_byte(self.MUX_ADDRESS, 1 << self.mux_channel)
            cmd = self._SINGLE_WRITE_CMD | (self.dac_channel << 1)
            self.i2c.write_i2c_block_data(
                self.DAC_ADDRESS,
                cmd,
                [self._HI_BITS | ((raw >> 8) & 0x0F), raw & 0xFF],
            )
            return True
        except Exception as e:
            self.send_warning(
                summary="i2c-dac-write-failed",
                details=f"{self.name}: raw={raw} mux_ch={self.mux_channel} "
                f"dac_ch={self.dac_channel}: {e}",
            )
            return False

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.HEARTBEAT_S * 2)]

    def start(self) -> None:
        self.services.add_task(
            asyncio.create_task(self._heartbeat(), name=f"{self.name}-heartbeat")
        )

    async def _heartbeat(self) -> None:
        """Watchdog pat + drift enforcement: re-assert the last commanded
        value every period, healing anything that cleared the DAC (a supply
        blip, another process's mux collision)."""
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            self._write_dac()
            await asyncio.sleep(self.HEARTBEAT_S)

    def stop(self) -> None:
        self._stop_requested = True

    async def join(self) -> None:
        ...
