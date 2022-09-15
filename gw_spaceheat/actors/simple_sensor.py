import time
from typing import List

from actors.actor_base import ActorBase
from actors.utils import Subscription, responsive_sleep
from config import ScadaSettings
from data_classes.hardware_layout import HardwareLayout
from data_classes.node_config import NodeConfig
from data_classes.sh_node import ShNode
from schema.gt.gt_telemetry.gt_telemetry_maker import GtTelemetry_Maker


class SimpleSensor(ActorBase):
    MAIN_LOOP_MIN_TIME_S = 0.2

    def __init__(self, alias: str, settings: ScadaSettings, hardware_layout: HardwareLayout):
        super(SimpleSensor, self).__init__(alias=alias, settings=settings, hardware_layout=hardware_layout)
        self._last_sent_s = 0
        self.telemetry_value = None
        self.config = NodeConfig(self.node, settings)
        self.screen_print(f"Initialized {self.__class__}")

    def subscriptions(self) -> List[Subscription]:
        return []

    def on_message(self, from_node: ShNode, payload):
        pass

    def report_telemetry(self):
        """Publish the telemetry value, using exponent and telemetry_name from
        self.config.reporting"""
        if self.telemetry_value is None:
            return
        telemetry_name = self.config.reporting.TelemetryName
        exponent = self.config.reporting.Exponent
        now_s = time.time()
        payload = GtTelemetry_Maker(
            name=telemetry_name,
            value=int(self.telemetry_value),
            exponent=exponent,
            scada_read_time_unix_ms=int(now_s * 1000),
        ).tuple
        self.publish(payload)
        self._last_sent_s = int(now_s)
        self.screen_print(f"{payload.Value} {telemetry_name.value}")
        # self.screen_print(f"{int(time_of_read_s * 1000)}")

    def is_time_to_report(self) -> bool:
        """Returns True if it is time to report, The sensor is supposed to report every
        self.config.reporting.SamplePeriodS seconds - that is, if this number is 5, then
        the report will happen ASAP after top of the hour, then again 5 seconds later, etc ).
        """
        now_s = time.time()
        if int(now_s) == self._last_sent_s:
            return False
        elif now_s - self._last_sent_s >= self.config.reporting.SamplePeriodS:
            return True
        else:
            return False

    def update_telemetry_value(self):
        """Updates self.telemetry_value, using the config.driver"""
        self.telemetry_value = self.config.driver.read_telemetry_value()

    def main(self):
        self._main_loop_running = True
        while self._main_loop_running is True:
            loop_start_s = time.time()
            self.update_telemetry_value()
            if self.is_time_to_report():
                self.report_telemetry()
            now_s = time.time()
            if (now_s - loop_start_s) < self.MAIN_LOOP_MIN_TIME_S:
                wait_time_s = self.MAIN_LOOP_MIN_TIME_S - (now_s - loop_start_s)
                responsive_sleep(self, wait_time_s)
