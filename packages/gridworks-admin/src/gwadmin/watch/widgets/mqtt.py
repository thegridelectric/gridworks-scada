from textual.messages import Message
from textual.reactive import Reactive
from textual.reactive import reactive

from textual.widget import Widget

from gwadmin.watch.clients.constrained_mqtt_client import ConstrainedMQTTClient


class Mqtt(Widget):

    class StateChange(Message):

        def __init__(self, old_state: str, new_state: str) -> None:
            self.old_state = old_state
            self.new_state = new_state
            super().__init__()

    class Receipt(Message):

        def __init__(self, topic: str, payload: bytes) -> None:
            self.topic = topic
            self.payload = payload
            super().__init__()

    def change_state(self, old_state: str, new_state: str) -> None:
        self.post_message(Mqtt.StateChange(old_state, new_state))

    def mqtt_receipt(self, topic: str, payload: bytes) -> None:
        self.post_message(Mqtt.Receipt(topic, payload))

class MqttState(Widget):

    mqtt_state: Reactive[str] = reactive(ConstrainedMQTTClient.States.stopped, layout=True)
    message_count: Reactive[int] = reactive(0, layout=True)
    snapshot_count: Reactive[int] = reactive(0, layout=True)
    layout_count: Reactive[int] = reactive(0, layout=True)

    def render(self) -> str:
        if self.mqtt_state == ConstrainedMQTTClient.States.active:
            color = "green"
        else:
            color = "red"
        return (
            f"MQTT broker connection: [{color}]{self.mqtt_state:12s}[/{color}]"

            # Counters disabled as defense against memory leaks:
            # f"  Messages received: {self.message_count}  "
            # f"Snapshots: {self.snapshot_count}  "
            # f"Layouts: {self.layout_count}"
        )
