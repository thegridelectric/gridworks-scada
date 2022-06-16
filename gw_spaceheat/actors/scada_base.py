import uuid
from abc import abstractmethod
from typing import List

import helpers
import paho.mqtt.client as mqtt
import settings
from data_classes.sh_node import ShNode
from schema.gs.gs_dispatch_maker import GsDispatch, GsDispatch_Maker
from schema.gs.gs_pwr import GsPwr
from schema.gt.gt_telemetry.gt_telemetry import GtTelemetry
from schema.schema_switcher import TypeMakerByAliasDict

from actors.actor_base import ActorBase
from actors.utils import QOS, Subscription


class ScadaBase(ActorBase):
    def __init__(self, node: ShNode):
        super(ScadaBase, self).__init__(node=node)
        self.gwMqttBroker = settings.GW_MQTT_BROKER_ADDRESS
        self.gw_publish_client_id = ('-').join(str(uuid.uuid4()).split('-')[:-1])
        self.gw_publish_client = mqtt.Client(self.gw_publish_client_id)
        self.gw_publish_client.username_pw_set(username=settings.GW_MQTT_USER_NAME,
                                               password=helpers.get_secret('GW_MQTT_PW'))
        self.gw_publish_client.connect(self.gwMqttBroker)
        self.gw_publish_client.loop_start()
        if self.logging_on:
            self.gw_publish_client.on_log = self.on_log
        self.gw_consume_client_id = ('-').join(str(uuid.uuid4()).split('-')[:-1])
        self.gw_consume_client = mqtt.Client(self.gw_consume_client_id)
        self.gw_consume_client.username_pw_set(username=settings.GW_MQTT_USER_NAME,
                                               password=helpers.get_secret('GW_MQTT_PW'))
        self.gw_consume_client.connect(self.gwMqttBroker)
        if self.logging_on:
            self.gw_consume_client.on_log = self.on_log
        self.gw_consume_client.subscribe(list(map(lambda x: (f"{x.Topic}", x.Qos.value), self.gw_subscriptions())))
        self.gw_consume_client.on_message = self.on_gw_mqtt_message

    def gw_subscriptions(self) -> List[Subscription]:
        return [Subscription(Topic=f'{settings.ATN_G_NODE_ALIAS}/{GsDispatch_Maker.type_alias}', Qos=QOS.AtMostOnce)]

    def on_gw_mqtt_message(self, client, userdata, message):
        try:
            (from_alias, type_alias) = message.topic.split('/')
        except IndexError:
            raise Exception("topic must be of format A/B")
        if from_alias != settings.ATN_G_NODE_ALIAS:
            raise Exception(f"alias {from_alias} not my AtomicTNode!")
        from_node = ShNode.by_alias['a']
        if type_alias not in TypeMakerByAliasDict.keys():
            raise Exception(f"Type {type_alias} not recognized. Should be in TypeByAliasDict keys!")
        payload_as_tuple = TypeMakerByAliasDict[type_alias].type_to_tuple(message.payload)
        self.on_gw_message(from_node=from_node, payload=payload_as_tuple)

    @abstractmethod
    def on_gw_message(self, from_node: ShNode, payload: GtTelemetry):
        raise NotImplementedError

    def gw_publish(self, payload: GtTelemetry):
        if type(payload) in [GsPwr, GsDispatch]:
            qos = QOS.AtMostOnce
        else:
            qos = QOS.AtLeastOnce
        self.gw_publish_client.publish(
            topic=f'{helpers.scada_g_node_alias()}/{payload.TypeAlias}',
            payload=payload.as_type(),
            qos=qos.value,
            retain=False)

    def start(self):
        self.publish_client.loop_start()
        self.consume_client.loop_start()
        self.gw_consume_client.loop_start()
        self.gw_publish_client.loop_start()
        self.main_thread.start()
        self.screen_print(f'Started {self.__class__}')

    def stop(self):
        self.screen_print("Stopping ...")
        self.consume_client.loop_stop()
        self.gw_consume_client.loop_stop()
        self.terminate_main_loop()
        self.main_thread.join()
        self.publish_client.loop_stop()
        self.gw_publish_client.loop_stop()
        self.screen_print("Stopped")
