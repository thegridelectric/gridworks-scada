import logging
import sys
from logging import Logger
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import HorizontalGroup
from textual.containers import Vertical
from textual.logging import TextualHandler
from textual.messages import Message
from textual.reactive import Reactive
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable
from textual.widgets import Select
from textual.widgets import Static
from textual.widgets._data_table import CellType  # noqa

from gwadmin.config import DEFAULT_ADMIN_TIMEOUT
from gwadmin.watch.clients.constrained_mqtt_client import ConstrainedMQTTClient
from gwadmin.watch.clients.relay_client import ObservedRelayStateChange
from gwadmin.watch.clients.relay_client import RelayClientCallbacks
from gwadmin.watch.clients.relay_client import RelayConfigChange
from gwadmin.watch.widgets.keepalive import KeepAliveButton
from gwadmin.watch.widgets.keepalive import ReleaseControlButton
from gwadmin.watch.widgets.mqtt import Mqtt
from gwadmin.watch.widgets.mqtt import MqttState
from gwadmin.watch.widgets.relay_toggle_button import RelayToggleButton
from gwadmin.watch.widgets.relay_widget_info import RelayWidgetConfig
from gwadmin.watch.widgets.relay_widget_info import RelayWidgetInfo
from gwadmin.watch.widgets.time_input import TimeInput
from gwadmin.watch.widgets.timer import TimerDigits
from gwsproto.named_types import LayoutLite
from gwsproto.named_types import SnapshotSpaceheat

module_logger = logging.getLogger(__name__)
module_logger.addHandler(TextualHandler())

class Relays(Widget):
    BINDINGS = [
        ("n", "toggle_relay", "Toggle selected relay"),
    ]

    mqtt_state: Reactive[str] = reactive(ConstrainedMQTTClient.States.stopped)
    state_colors: Reactive[bool] = reactive(False)
    curr_energized: Reactive[Optional[bool]] = reactive(None)
    curr_config: Reactive[RelayWidgetConfig] = reactive(RelayWidgetConfig)
    logger: Logger
    _relays: dict[str, RelayWidgetInfo]
    _scadas: list[str]
    _initial_scada: str
    _default_timeout_seconds: int = DEFAULT_ADMIN_TIMEOUT

    class RelayStateChange(Message):
        def __init__(self, changes: dict[str, ObservedRelayStateChange]) -> None:
            self.changes = changes
            super().__init__()

    class ConfigChange(Message):
        def __init__(self, changes: dict[str, RelayConfigChange]) -> None:
            self.changes = changes
            super().__init__()

    class Snapshot(Message):
        def __init__(self, snapshot: SnapshotSpaceheat) -> None:
            self.snapshot = snapshot
            super().__init__()

    class Layout(Message):
        def __init__(self, layout: LayoutLite) -> None:
            self.layout = layout
            super().__init__()

    def __init__(
        self,
        scadas: list[str],
        initial_scada: str,
        default_timeout_seconds: int = DEFAULT_ADMIN_TIMEOUT,
        logger: Optional[Logger] = None,
        **kwargs
    ) -> None:
        self._scadas = scadas
        self._initial_scada = initial_scada
        self._default_timeout_seconds = default_timeout_seconds
        self.logger = logger or module_logger
        self._relays = {}
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield MqttState(id="mqtt_state")
            yield Horizontal(
                Static("Select Scada: ", classes="label"),
                Select(
                    ((scada, scada) for scada in self._scadas),
                    prompt="Scada",
                    value=self._initial_scada,
                    id="select_scada",
                ),
                classes="container",
            )
            with HorizontalGroup():
                yield KeepAliveButton(default_timeout_seconds=self._default_timeout_seconds)
                yield ReleaseControlButton(default_timeout_seconds=self._default_timeout_seconds)
                yield TimeInput(default_timeout_seconds=self._default_timeout_seconds)
                yield TimerDigits(default_timeout_seconds=self._default_timeout_seconds)
            yield DataTable(
                id="relays_table",
                zebra_stripes=True,
                cursor_type="row",
            )
            with HorizontalGroup(
                id="relay_toggle_button_container",
            ):
                yield RelayToggleButton(
                    label="bar",
                    id="relay_toggle_button",
                ).data_bind(
                    energized=Relays.curr_energized,
                    config=Relays.curr_config,
                )
            # yield DataTable(
            #     id="message_table",
            #     classes="undisplayed",
            # )

    def on_mount(self) -> None:
        data_table = self.query_one("#relays_table", DataTable)
        for column_name, width in [
            ("Relay", None),
            ("Name", 25),
            ("Current state", 25),
            ("Action", 25),
            ("Energized", None),
        ]:
            data_table.add_column(column_name, key=column_name, width=width)
        # message_table = self.query_one("#message_table", DataTable)
        # message_table.add_columns(
        # "Time", "Type", "Payload",
        # )

    def _get_relay_row_data(self, relay_name: str) -> dict[str, CellType]:
        if relay_name in self._relays:
            relay = self._relays[relay_name]
            return {
                "Relay": relay.config.table_name.relay_number,
                "Name": relay.config.table_name.row_name,
                "Current state": relay.config.get_current_state_str(relay.get_state()),
                "Action": relay.config.get_state_str(not relay.get_state(), show_icon=False),
                "Energized": relay.config.get_current_state_str(relay.get_state(), icon=True),
            }
        return {}

    def on_relays_relay_state_change(self, message: RelayStateChange) -> None:
        for relay_name, change in message.changes.items():
            relay_info = self._relays.get(relay_name, None)
            if relay_info is not None:
                new_state = RelayWidgetInfo.get_observed_state(change.new_state)
                if new_state != relay_info.get_state():
                    relay_info.observed = change.new_state
                    self._update_relay_row(relay_name)
                table = self.query_one("#relays_table", DataTable)
                relay_idx = table.get_row_index(relay_name)
                if relay_idx == table.cursor_row:
                    self._update_buttons(relay_name)


    def _get_relay_row(self, relay_name: str) -> list[str | CellType]:
        return list(self._get_relay_row_data(relay_name).values())

    def _update_relay_row(self, relay_name: str) -> None:
        table = self.query_one("#relays_table", DataTable)
        data = self._get_relay_row_data(relay_name)
        for column_name, value in data.items():
            table.update_cell(
                relay_name,
                column_name,
                value,
                update_width=column_name=="State",
            )

    def on_relays_config_change(self, message: ConfigChange) -> None:
        message.prevent_default()
        table = self.query_one("#relays_table", DataTable)
        for relay_name, change in message.changes.items():
            relay_info = self._relays.get(relay_name, None)
            if relay_info is not None:
                if change.new_config is None:
                    self._relays.pop(relay_name)
                    table.remove_row(relay_name)
                else:
                    new_config = RelayWidgetConfig.from_config(change.new_config)
                    if new_config != relay_info.config:
                        relay_info.config = new_config
                        self._update_relay_row(relay_name)
            else:
                if change.new_config is not None:
                    self._relays[relay_name] = RelayWidgetInfo(
                        config=RelayWidgetConfig.from_config(change.new_config)
                    )
                    table.add_row(
                        *self._get_relay_row(relay_name),
                        key=relay_name
                    )
        table.sort(
            "Relay",
            "Name",
            key=lambda row: (row[0], row[1]) if row[0] is not None else (sys.maxsize, row[1]),
        )
        self.logger.info("--on_relays_config_change")

    def _update_buttons(self, relay_name: str) -> None:
        relay_info = self._relays[relay_name]
        self.curr_energized = relay_info.get_state()
        self.curr_config = relay_info.config
        self.query_one(
            "#relay_toggle_button_container",
            HorizontalGroup,
        ).border_title = relay_info.config.table_name.border_title

    def on_data_table_row_highlighted(self, message: DataTable.RowHighlighted) -> None:
        self._update_relay_row(message.row_key.value)
        self._update_buttons(message.row_key.value)

    def on_relays_layout(self, message: Layout) -> None:  # noqa
        self.query_one(MqttState).message_count += 1
        self.query_one(MqttState).layout_count += 1
        # self.query_one("#message_table", DataTable).add_row(
        #     datetime.datetime.now(),
        #     type_name(LayoutLite),
        #     message.layout,
        # )
        # self.query_one("#message_table", DataTable).scroll_end()

    def on_relays_snapshot(self, message: Snapshot) -> None:  # noqa
        self.query_one(MqttState).message_count += 1
        self.query_one(MqttState).snapshot_count += 1
        # self.query_one("#message_table", DataTable).add_row(
        #     datetime.datetime.now(),
        #     type_name(SnapshotSpaceheat),
        #     message.snapshot,
        # )
        # self.query_one("#message_table", DataTable).scroll_end()
    
    def on_mqtt_state_change(self, message: Mqtt.StateChange):
        self.query_one(MqttState).mqtt_state = message.new_state

    def on_mqtt_receipt(self, message: Mqtt.Receipt):  # noqa
        self.query_one(MqttState).message_count += 1
        # payload = json.loads(message.payload.decode("utf-8"))
        # self.query_one("#message_table", DataTable).add_row(
        #     datetime.datetime.now(),
        #     MQTTTopic.decode(message.topic).message_type,
        #     str(payload.get("Payload", payload))
        # )
        # self.query_one("#message_table", DataTable).scroll_end()

    def action_toggle_relay(self) -> None:
        self.query_one(
            "#relay_toggle_button",
            RelayToggleButton
        ).action_toggle_relay()

    def relay_client_callbacks(self) -> RelayClientCallbacks:
        return RelayClientCallbacks(
            mqtt_state_change_callback=self.mqtt_state_change_callback,
            relay_state_change_callback=self.relay_state_change_callback,
            relay_config_change_callback=self.relay_config_change_callback,
            # disable these as defense against memroy leaks
            mqtt_message_received_callback=None,
            layout_callback=None,
            snapshot_callback=None,
        )

    def relay_state_change_callback(self, changes: dict[str, ObservedRelayStateChange]) -> None:
        self.post_message(Relays.RelayStateChange(changes))

    def relay_config_change_callback(self, changes: dict[str, RelayConfigChange]) -> None:
        self.post_message(Relays.ConfigChange(changes))

    def layout_callback(self, layout: LayoutLite) -> None:
        self.post_message(Relays.Layout(layout))

    def snapshot_callback(self, snapshot: SnapshotSpaceheat) -> None:
        self.post_message(Relays.Snapshot(snapshot))

    def mqtt_state_change_callback(self, old_state: str, new_state: str) -> None:
        self.post_message(Mqtt.StateChange(old_state, new_state))

    def mqtt_receipt_callback(self, topic: str, payload: bytes) -> None:
        self.post_message(Mqtt.Receipt(topic, payload))

