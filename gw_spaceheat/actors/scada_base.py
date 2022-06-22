import uuid
from abc import abstractmethod

import helpers
import paho.mqtt.client as mqtt
import settings
from data_classes.sh_node import ShNode
from schema.gs.gs_dispatch_maker import GsDispatch
from schema.gs.gs_pwr import GsPwr
from schema.schema_switcher import TypeMakerByAliasDict

from actors.actor_base import ActorBase
from actors.utils import QOS


class ScadaBase(ActorBase):

    def __init__(self, node: ShNode, logging_on=False):
        super(ScadaBase, self).__init__(node=node, logging_on=logging_on)
        self.gwMqttBroker = settings.GW_MQTT_BROKER_ADDRESS
        self.gw_publish_client_id = "-".join(str(uuid.uuid4()).split("-")[:-1])
        self.gw_publish_client = mqtt.Client(self.gw_publish_client_id)
        self.gw_publish_client.username_pw_set(
            username=settings.GW_MQTT_USER_NAME, password=helpers.get_secret("GW_MQTT_PW")
        )
        self.gw_publish_client.on_connect = self.on_gw_publish_connect
        self.gw_publish_client.on_connect_fail = self.on_gw_publish_connect_fail
        self.gw_publish_client.on_disconnect = self.on_gw_publish_disconnect
        if self.logging_on:
            self.gw_publish_client.on_log = self.on_log
        self.gw_consume_client_id = "-".join(str(uuid.uuid4()).split("-")[:-1])
        self.gw_consume_client = mqtt.Client(self.gw_consume_client_id)
        self.gw_consume_client.username_pw_set(
            username=settings.GW_MQTT_USER_NAME, password=helpers.get_secret("GW_MQTT_PW")
        )
        self.gw_consume_client.on_message = self.on_gw_mqtt_message
        self.gw_consume_client.on_connect = self.on_gw_consume_connect
        self.gw_consume_client.on_connect_fail = self.on_gw_consume_connect_fail
        self.gw_consume_client.on_disconnect = self.on_gw_consume_disconnect
        if self.logging_on:
            self.gw_consume_client.on_log = self.on_log

    def subscribe_gw_consume_client(self):
        self.gw_consume_client.subscribe(
            list(map(lambda x: (f"{x.Topic}", x.Qos.value), self.gw_subscriptions()))
        )

    @abstractmethod
    def gw_subscriptions(self):
        raise NotImplementedError

    # noinspection PyUnusedLocal
    def on_gw_publish_connect(self, client, userdata, flags, rc):
        self.mqtt_log_hack(
            [
                f"({helpers.log_time()}) GW Publish Connected flags {str(flags)} + result code {str(rc)} + "
                f" userdata {str(userdata)}"
            ]
        )

    # noinspection PyUnusedLocal
    def on_gw_publish_connect_fail(self, client, userdata, rc):
        self.mqtt_log_hack(
            [f"({helpers.log_time()}) GW Publish Connect fail! result code {str(rc)}"]
        )

    # noinspection PyUnusedLocal
    def on_gw_publish_disconnect(self, client, userdata, rc):
        self.mqtt_log_hack(
            [f"({helpers.log_time()}) GW Publish disconnected! result code {str(rc)}"]
        )

    # noinspection PyUnusedLocal
    def on_gw_consume_connect(self, client, userdata, flags, rc):
        self.mqtt_log_hack(
            [
                f"({helpers.log_time()}) GW Consume Connected flags {str(flags)} + result code {str(rc)}"
            ]
        )
        self.subscribe_gw_consume_client()

    # noinspection PyUnusedLocal

    def on_gw_consume_connect_fail(self, client, userdata, rc):
        self.mqtt_log_hack(
            [f"({helpers.log_time()}) GW Consume Connect fail! result code {str(rc)}"]
        )

    # noinspection PyUnusedLocal
    def on_gw_consume_disconnect(self, client, userdata, rc):
        self.mqtt_log_hack(
            [f"({helpers.log_time()}) GW Consume disconnected! result code {str(rc)}"]
        )

    # noinspection PyUnusedLocal
    def on_gw_mqtt_message(self, client, userdata, message):
        try:
            (from_alias, type_alias) = message.topic.split("/")
        except IndexError:
            raise Exception("topic must be of format A/B")
        if from_alias != settings.ATN_G_NODE_ALIAS:
            raise Exception(f"alias {from_alias} not my AtomicTNode!")
        from_node = ShNode.by_alias["a"]
        if type_alias not in TypeMakerByAliasDict.keys():
            raise Exception(f"Type {type_alias} not recognized. Should be in TypeByAliasDict keys!")
        payload_as_tuple = TypeMakerByAliasDict[type_alias].type_to_tuple(message.payload)
        self.on_gw_message(from_node=from_node, payload=payload_as_tuple)

    @abstractmethod
    def on_gw_message(self, from_node: ShNode, payload):
        raise NotImplementedError

    def gw_publish(self, payload):
        if type(payload) in [GsPwr, GsDispatch]:
            qos = QOS.AtMostOnce
        else:
            qos = QOS.AtLeastOnce
        topic = f"{helpers.scada_g_node_alias()}/{payload.TypeAlias}"
        self.gw_publish_client.publish(
            topic=topic,
            payload=payload.as_type(),
            qos=qos.value,
            retain=False,
        )

    def start(self):
        super().start()
        self.screen_print("howdy")
        self.gw_publish_client.connect(self.gwMqttBroker)
        self.gw_consume_client.connect(self.gwMqttBroker)
        self.gw_publish_client.loop_start()
        self.gw_consume_client.loop_start()
        self.screen_print(f"Started {self.__class__} remote connections")

    def stop(self):
        super().stop()
        self.gw_consume_client.loop_stop()
        self.gw_publish_client.loop_stop()
        self.screen_print(f"Stopped {self.__class__}")
