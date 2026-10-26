import logging
from logging import Logger
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import HorizontalGroup
from textual.logging import TextualHandler
from textual.messages import Message
from textual.reactive import Reactive
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable
from textual.widgets._data_table import CellType  # noqa

from gwadmin.config import DEFAULT_ADMIN_TIMEOUT
from gwadmin.watch.clients.constrained_mqtt_client import ConstrainedMQTTClient
from gwadmin.watch.clients.dispatch_replies import DispatchReply
from gwadmin.watch.clients.relay_client import ObservedRelayStateChange
from gwadmin.watch.clients.relay_client import RelayClientCallbacks
from gwadmin.watch.clients.relay_client import RelayConfig
from gwadmin.watch.clients.relay_client import RelayConfigChange
from gwadmin.watch.widgets.mqtt import Mqtt
from gwadmin.watch.widgets.mqtt import MqttState
from gwadmin.watch.widgets.relay_toggle_button import RelayToggleButton
from gwadmin.watch.widgets.relay_widget_info import RelayWidgetConfig
from gwadmin.watch.widgets.relay_widget_info import RelayWidgetInfo
from gwsproto.named_types import LayoutLite
from gwsproto.named_types import SnapshotSpaceheat

module_logger = logging.getLogger(__name__)
module_logger.addHandler(TextualHandler())

class Relays(Widget):
    BINDINGS = [
        ("n", "toggle_relay(0)", "Send selected row's first command"),
        ("p", "toggle_relay(1)", "Send selected row's second command"),
    ]

    mqtt_state: Reactive[str] = reactive(ConstrainedMQTTClient.States.stopped)
    state_colors: Reactive[bool] = reactive(False)
    curr_state: Reactive[Optional[str]] = reactive(None)
    curr_config: Reactive[Optional[RelayWidgetConfig]] = reactive(None)
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

    class DispatchReplied(Message):
        def __init__(self, reply: DispatchReply) -> None:
            self.reply = reply
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
        h = Horizontal(
            DataTable(
                id="relays_table",
                zebra_stripes=True,
                cursor_type="row",
                classes="subsection"
            ),
            HorizontalGroup(
                *[
                    RelayToggleButton(
                        offer_index=offer_index,
                        label="bar",
                        id=f"relay_toggle_button_{offer_index}",
                        classes="relay_toggle_button",
                    ).data_bind(
                        state=Relays.curr_state,
                        config=Relays.curr_config,
                    )
                    for offer_index in range(2)
                ],
                id="relay_toggle_button_container",
                classes="subsection",
            ),
            id="relays_container"
        )
        h.border_title = "Relays"
        yield h

    def on_mount(self) -> None:
        data_table = self.query_one("#relays_table", DataTable)
        for column_name, width in [
            ("Name", 30),
            ("Current state", 25),
            ("Action", 25),
        ]:
            data_table.add_column(column_name, key=column_name, width=width)

    def _get_relay_row_data(self, relay_name: str) -> dict[str, CellType]:
        if relay_name in self._relays:
            relay = self._relays[relay_name]
            return {
                "Name": self.row_name(relay.config),
                "Current state": relay.config.get_current_state_str(relay.get_state()),
                "Action": relay.config.get_action_str(relay.get_state()),
            }
        return {}

    def on_relays_relay_state_change(self, message: RelayStateChange) -> None:
        for relay_name, change in message.changes.items():
            relay_info = self._relays.get(relay_name, None)
            if relay_info is not None:
                if change.new_state != relay_info.observed:
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
        self.logger.debug("++on_relays_config_change  changes: %d ", len(message.changes))
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
        self._sort_rows(table)
        if table.is_valid_coordinate(table.cursor_coordinate):
            selected_row_key = table.coordinate_to_cell_key(table.cursor_coordinate)[0]
        else:
            selected_row_key = ""
        self._update_buttons(selected_row_key)
        self.logger.debug("--on_relays_config_change: selected row key: %s", selected_row_key.value if selected_row_key!="" else "")

    @staticmethod
    def owner_chain(config: RelayConfig, configs: dict[str, RelayConfig]) -> tuple[str, ...]:
        """The node's owners from the top down, ending with the node itself
        (five-v-boss, pico-cycler, vdc-relay for the vdc relay)."""
        chain = [config.about_node_name]
        owner = config.owner
        while owner is not None and owner not in chain:
            chain.append(owner)
            above = configs.get(owner)
            owner = above.owner if above is not None else None
        return tuple(reversed(chain))

    @classmethod
    def row_order_key(cls, config: RelayConfig, configs: dict[str, RelayConfig]) -> tuple[str, ...]:
        """Rows sort by name, except that a node owned by an interior
        command node sits directly under its owner's row, however deep the
        chain (vdc-relay under pico-cycler under five-v-boss,
        hp-scada-ops-relay under hp-boss). The key is the owner chain from
        the top, so a node sorts right after its owner."""
        return cls.owner_chain(config, configs)

    @staticmethod
    def row_name(config: RelayWidgetConfig) -> str:
        """The Name cell: a node owned by an interior command node is
        indented one step, whatever its depth, so the owned rows line up
        under their owners."""
        indent = "  " if config.owner is not None else ""
        return indent + config.table_name.row_name

    def _configs(self) -> dict[str, RelayConfig]:
        return {info.config.about_node_name: info.config for info in self._relays.values()}

    def _sort_rows(self, table: DataTable) -> None:
        configs = self._configs()
        keys = {
            self.row_name(info.config): self.row_order_key(info.config, configs)
            for info in self._relays.values()
        }
        table.sort("Name", key=lambda name: keys[name])

    def _update_buttons(self, relay_name: str) -> None:
        self.logger.debug("++Relays._update_buttons: %s", relay_name)
        relay_info = self._relays.get(relay_name)
        if relay_info is not None:
            curr_state = relay_info.get_state()
            curr_config = relay_info.config
            curr_title = relay_info.config.table_name.border_title
        else:
            curr_state = None
            curr_config = None
            curr_title = ""
        self.curr_state = curr_state
        self.curr_config = curr_config
        self.query_one(
            "#relay_toggle_button_container",
            HorizontalGroup,
        ).border_title = curr_title
        self.logger.debug("--Relays._update_buttons: %s  %s", relay_name, curr_title)

    def on_data_table_row_highlighted(self, message: DataTable.RowHighlighted) -> None:
        self._update_relay_row(message.row_key.value if message.row_key is not None else "")
        self._update_buttons(message.row_key.value if message.row_key is not None else "")

    def on_relays_layout(self, message: Layout) -> None:  # noqa
        self.app.query_one(MqttState).message_count += 1
        self.app.query_one(MqttState).layout_count += 1

    def on_relays_snapshot(self, message: Snapshot) -> None:  # noqa
        self.app.query_one(MqttState).message_count += 1
        self.app.query_one(MqttState).snapshot_count += 1

    def on_mqtt_state_change(self, message: Mqtt.StateChange):
        self.app.query_one(MqttState).mqtt_state = message.new_state

    def on_mqtt_receipt(self, message: Mqtt.Receipt):  # noqa
        self.app.query_one(MqttState).message_count += 1

    def action_toggle_relay(self, offer_index: int) -> None:
        self.query_one(
            f"#relay_toggle_button_{offer_index}",
            RelayToggleButton
        ).action_toggle_relay()


    def relay_client_callbacks(self) -> RelayClientCallbacks:
        return RelayClientCallbacks(
            mqtt_state_change_callback=self.mqtt_state_change_callback,
            relay_state_change_callback=self.relay_state_change_callback,
            relay_config_change_callback=self.relay_config_change_callback,
            dispatch_reply_callback=self.dispatch_reply_callback,
            # disable these as defense against memroy leaks
            mqtt_message_received_callback=None,
            ctrl_capabilities_callback=None,
            snapshot_callback=None,
        )

    def relay_state_change_callback(self, changes: dict[str, ObservedRelayStateChange]) -> None:
        self.post_message(Relays.RelayStateChange(changes))

    def relay_config_change_callback(self, changes: dict[str, RelayConfigChange]) -> None:
        self.post_message(Relays.ConfigChange(changes))

    def dispatch_reply_callback(self, reply: DispatchReply) -> None:
        self.post_message(Relays.DispatchReplied(reply))

    def layout_callback(self, layout: LayoutLite) -> None:
        self.post_message(Relays.Layout(layout))

    def snapshot_callback(self, snapshot: SnapshotSpaceheat) -> None:
        self.post_message(Relays.Snapshot(snapshot))

    def mqtt_state_change_callback(self, old_state: str, new_state: str) -> None:
        self.post_message(Mqtt.StateChange(old_state, new_state))

    def mqtt_receipt_callback(self, topic: str, payload: bytes) -> None:
        self.post_message(Mqtt.Receipt(topic, payload))

