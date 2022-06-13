
import threading
import time
from actors.atn.atn_base import Atn_Base
from data_classes.sh_node import ShNode
from schema.gs.gs_pwr import GsPwr
from schema.gt.gt_telemetry.gt_telemetry import GtTelemetry


class Atn(Atn_Base):
    def __init__(self, node: ShNode):
        super(Atn, self).__init__(node=node)
        self.total_power_w = 0
        self.gw_consume()
        self.schedule_thread = threading.Thread(target=self.main)
        self.schedule_thread.start()
        self.screen_print(f'Started {self.__class__}')

    def gs_pwr_received(self, payload: GsPwr, from_g_node_alias: str):
        self.screen_print(f"Got {payload} from {from_g_node_alias}")
        self.total_power_w = payload.Power

    def terminate_scheduling(self):
        self._scheduler_running = False

    def main(self):
        self._scheduler_running = True
        while self._scheduler_running is True:
            # track time and send status every x minutes (likely 5)
            time.sleep(1)

