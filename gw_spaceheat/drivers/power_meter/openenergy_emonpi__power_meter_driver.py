from typing import Optional
from config import ScadaSettings
import uuid
from actors.utils import QOS, Subscription
import paho.mqtt.client as mqtt
from drivers.power_meter.power_meter_driver import PowerMeterDriver
from data_classes.components.electric_meter_component import ElectricMeterComponent

from schema.enums import MakeModel


class OpenenergyEmonpi_PowerMeterDriver(PowerMeterDriver):
    def __init__(self, component: ElectricMeterComponent, settings: ScadaSettings):
        super(OpenenergyEmonpi_PowerMeterDriver, self).__init__(component=component)
        if component.cac.make_model != MakeModel.OPENENERGY__EMONPI:
            raise Exception(f"Expected {MakeModel.OPENENERGY__EMONPI}, got {component.cac}")
        self.component = component
        self.power_w: Optional[int] = None
        self.voltage_rms: Optional[float] = None

        self.settings = settings
        self.client_id = "-".join(str(uuid.uuid4()).split("-")[:-1])
        self.client = mqtt.Client(self.client_id)
        self.client.username_pw_set(
            username=self.settings.local_mqtt.username,
            password=self.settings.local_mqtt.password.get_secret_value(),
        )
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_mqtt_message
        self.start()

    def on_connect(self, client, userdata, flags, rc):
        self.subscribe()

    def subscriptions(self):
        return [Subscription(Topic="emon/emonpi/power1", Qos=QOS.AtMostOnce)]

    def subscribe(self):
        subscriptions = list(map(lambda x: (f"{x.Topic}", x.Qos.value), self.subscriptions()))
        if subscriptions:
            self.client.subscribe(subscriptions)

    def on_mqtt_message(self, client, userdata, message):
        try:
            (emon, emonpi, emon_telemetry_handle) = message.topic.split("/")
        except IndexError:
            raise Exception("topic must be of format A/B/C")
        if emon != 'emon' or emonpi != 'emonpi':
            raise Exception("topic must be of the form emon/emonpi/telemetry")

        self.on_message(emon_telemetry_handle=emon_telemetry_handle, payload=message.payload)

    def on_message(self, emon_telemetry_handle, payload):
        if emon_telemetry_handle == 'power1':
            self.power_w = int(payload)

    def read_current_rms_micro_amps(self) -> Optional[int]:
        raise NotImplementedError

    def read_hw_uid(self) -> Optional[str]:
        return "1001ab"

    def read_power_w(self) -> Optional[int]:
        return self.power_w

    def start(self):
        self.client.connect(self.settings.local_mqtt.host, port=self.settings.local_mqtt.port)
        self.client.loop_start()
