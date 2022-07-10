import uuid
from abc import abstractmethod

import paho.mqtt.client as mqtt

import helpers
import settings
from actors.actor_base import ActorBase
from actors.utils import QOS
from data_classes.sh_node import ShNode
from schema.gs.gs_dispatch_maker import GsDispatch
from schema.gs.gs_pwr import GsPwr
from schema.schema_switcher import TypeMakerByAliasDict


class ScadaBase(ActorBase):
    def __init__(self, node: ShNode, logging_on=False):
        super(ScadaBase, self).__init__(node=node, logging_on=logging_on)
        self.gwMqttBroker = settings.GW_MQTT_BROKER_ADDRESS
        self.gwMqttBrokerPort = getattr(settings, "GW_MQTT_BROKER_PORT", 1883)
        self.gw_client_id = "-".join(str(uuid.uuid4()).split("-")[:-1])
        self.gw_client = mqtt.Client(self.gw_client_id)
        self.gw_client.username_pw_set(
            username=settings.GW_MQTT_USER_NAME, password=helpers.get_secret("GW_MQTT_PW")
        )
        self.gw_client.on_message = self.on_gw_mqtt_message
        self.gw_client.on_connect = self.on_gw_connect
        self.gw_client.on_connect_fail = self.on_gw_connect_fail
        self.gw_client.on_disconnect = self.on_gw_disconnect
        if self.logging_on:
            self.gw_client.on_log = self.on_log

    def subscribe_gw(self):
        subscriptions = list(map(lambda x: (f"{x.Topic}", x.Qos.value), self.gw_subscriptions()))
        if subscriptions:
            self.gw_client.subscribe(subscriptions)

    @abstractmethod
    def gw_subscriptions(self):
        raise NotImplementedError

    # noinspection PyUnusedLocal
    def on_gw_connect(self, client, userdata, flags, rc):
        self.mqtt_log_hack(
            [
                f"({helpers.log_time()}) Cloud Mqtt client Connected flags {str(flags)} + result code {str(rc)}"
            ]
        )
        self.subscribe_gw()

    # noinspection PyUnusedLocal
    def on_gw_connect_fail(self, client, userdata, rc):
        self.mqtt_log_hack(
            [f"({helpers.log_time()}) Cloud Mqtt client Connect fail! result code {str(rc)}"]
        )

    # noinspection PyUnusedLocal
    def on_gw_disconnect(self, client, userdata, rc):
        self.mqtt_log_hack(
            [f"({helpers.log_time()}) Cloud Mqtt client disconnected! result code {str(rc)}"]
        )

    # noinspection PyUnusedLocal
    def on_gw_mqtt_message(self, client, userdata, message):
        try:
            (from_alias, type_alias) = message.topic.split("/")
        except IndexError:
            raise Exception("topic must be of format A/B")
        if from_alias != self.atn_g_node_alias:
            raise Exception(f"alias {from_alias} not my AtomicTNode!")
        if type_alias not in TypeMakerByAliasDict.keys():
            raise Exception(f"Type {type_alias} not recognized. Should be in TypeByAliasDict keys!")
        payload_as_tuple = TypeMakerByAliasDict[type_alias].type_to_tuple(message.payload)
        self.on_gw_message(payload=payload_as_tuple)

    @abstractmethod
    def on_gw_message(self, payload):
        raise NotImplementedError

    def gw_publish(self, payload):
        if type(payload) in [GsPwr, GsDispatch]:
            qos = QOS.AtMostOnce
        else:
            qos = QOS.AtLeastOnce
        self.gw_client.publish(
            topic=f"{self.scada_g_node_alias}/{payload.TypeAlias}",
            payload=payload.as_type(),
            qos=qos.value,
            retain=False,
        )

    def start(self):
        super().start()
        self.gw_client.connect(self.gwMqttBroker, port=self.gwMqttBrokerPort)
        self.gw_client.loop_start()
        self.screen_print(f"Started {self.__class__} remote connections")

    def stop(self):
        super().stop()
        self.gw_client.disconnect()
        self.gw_client.loop_stop()
        self.screen_print(f"Stopped {self.__class__}")
