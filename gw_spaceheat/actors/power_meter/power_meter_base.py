from typing import List
from actors.actor_base import ActorBase
from data_classes.sh_node import ShNode
from actors.mqtt_utils import Subscription, QOS
from schema.gs.gs_pwr_1_0_0_maker import GsPwr100_Maker, GsPwr100


class PowerMeterBase(ActorBase):
    def __init__(self, node: ShNode):
        super(PowerMeterBase, self).__init__(node=node)

    def subscriptions(self) -> List[Subscription]:
        return []

    def on_message(self, client, userdata, message):
        self.screen_print(f"{message.topic} subscription not implemented!")

    def publish_gs_pwr(self, payload: GsPwr100):
        topic = f'{self.node.alias}/{GsPwr100_Maker.mp_alias}'
        self.screen_print("Trying to publish")
        self.publish_client.publish(topic=topic, 
                            payload=payload.asbinary(),
                            qos = QOS.AtMostOnce.value,
                            retain=False)
