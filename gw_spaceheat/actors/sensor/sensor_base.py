import json
from typing import List

from actors.actor_base import ActorBase
from actors.mqtt_utils import QOS, Subscription
from data_classes.sh_node import ShNode
from schema.gt.gt_telemetry.gt_telemetry_1_0_1_maker import (
    GtTelemetry101, GtTelemetry101_Maker)


class SensorBase(ActorBase):
    def __init__(self, node: ShNode):
        super(SensorBase, self).__init__(node=node)

    def subscriptions(self) -> List[Subscription]:
        return []

    def on_message(self, client, userdata, message):
        self.screen_print(f"{message.topic} subscription not implemented!")

    def publish_gt_telemetry_1_0_1(self, payload: GtTelemetry101):
        topic = f'{self.node.alias}/{GtTelemetry101_Maker.mp_alias}'
        self.screen_print(f"Trying to publish {payload} to topic {topic}")
        self.publish_client.publish(topic=topic,
                                    payload=json.dumps(payload.asdict()),
                                    qos=QOS.AtLeastOnce.value,
                                    retain=False)
