import asyncio
import time
from typing import Sequence
from result import Err, Ok, Result

from gwproto.message import Message

from gwproactor import  MonitoredName
from gwproactor.message import PatInternalWatchdogMessage

from actors.sh_node_actor import ShNodeActor

from gwsproto.enums import GpioSenseMode, Unit
from gwsproto.data_classes.components import (
    Gw108GpioSensorComponent
)

from gwsproto.named_types import SingleReading
from scada_app_interface import ScadaAppInterface
class GpioSensor(ShNodeActor):
    """
    Reads a single GPIO input pin and publishes its raw logical state
    as a unitless data channel.
    """

    def __init__(self,
                 name: str,
                 services: ScadaAppInterface):
        
        super().__init__(name, services)

        self.component = self.node.component

        if not isinstance(self.component, Gw108GpioSensorComponent):
            raise ValueError(f"Component for {self.name} has type "
                             f"{type(self.component)}. Expected "
                             "I2cMultichannelDtRelayComponent or "
                             "Gw108GpioSensorComponent")

        # TODO later: add an actor that has a GPIO callback running
        # in a different thread and then use GPIO.add_event_detect
        # if for example we are counting pulses for a pulse meter
        if self.component.gt.SenseMode != GpioSenseMode.Polling:
            raise Exception("GpioSensor only works for Polling right now"
                            f", not {self.component.gt.SenseMode}")
        self.gpio_pin = self.component.gt.GpioPin
        self.send_to_derived = self.component.gt.SendToDerived
        self.cfg = self.component.gt.ConfigList[0] # must have exacty 1
        if self.cfg.Unit != Unit.Unitless:
            raise ValueError(f"unit for GpioSensor is unitless, not {self.cfg.Unit}")
        self.channel_name = self.cfg.ChannelName
        self.prev_value: int = 0
        self.latest_value: int = 0
        self._stop_requested = False

        if self.settings.is_simulated:
            self.GPIO = None
        else:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO

    def start(self):
        if self.GPIO:
            self.GPIO.setmode(self.GPIO.BCM)
            self.GPIO.setup(self.gpio_pin, self.GPIO.IN)

        self.services.add_task(
            asyncio.create_task(self.main(), name=f"{self.name}-main")
        )
        self.log(f"GpioSensor started on GPIO {self.gpio_pin}")

    def next_capture_time(self) -> float:
        now = time.time()
        period = self.cfg.CapturePeriodS
        return ((int(now) // period) + 1) * period

    def read_pin(self) -> bool:
        """ Update prev_value, latest_value,
        If value changed then return True. Else return False
        """
        if self.GPIO:
            raw = self.GPIO.input(self.gpio_pin)
            latest = 1 if raw else 0
        else:
            latest = 1 # TODO: create a simulated sensor later
        if latest != self.latest_value:
            self.prev_value = self.latest_value
            self.latest_value = latest
            return True
        return False

    def stop(self) -> None:
        """
        IOLoop will take care of shutting down webserver interaction.
        Here we stop periodic reporting task.
        """
        self._stop_requested = True

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""
        ...

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        ...

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, 120)]

    async def main(self):
        poll_period = (
            self.cfg.PollPeriodMs / 1000.0
            if self.cfg.PollPeriodMs
            else 1
        )

        period = self.cfg.CapturePeriodS
        next_capture_ts = ((int(time.time()) // period) + 1) * period

        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            changed = self.read_pin()

            # Async capture on change
            if self.cfg.AsyncCapture and changed:
                        self._publish()

            # Synchronous capture at exact period boundary
            if time.time() >= next_capture_ts:
                self._publish()
                next_capture_ts += period
    
            await asyncio.sleep(poll_period)

    def _publish(self):
        msg = SingleReading(
            ChannelName=self.channel_name,
            Value=self.latest_value,
            ScadaReadTimeUnixMs=int(time.time() * 1000)
        )
        self._send_to(
            self.primary_scada,
            msg,
        )
        if self.send_to_derived:
            self._send_to(
                self.derived_generator,
                msg,
            )

