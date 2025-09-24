import logging
from logging import Logger
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.logging import TextualHandler
from textual.messages import Message
from textual.widget import Widget
from textual.widgets import Button
from textual.widgets import DataTable
from textual.widgets import Input
from textual.widgets import Static
from textual.widgets._data_table import CellType  # noqa

from gwadmin.watch.clients.dac_client import DACClientCallbacks
from gwadmin.watch.clients.dac_client import DACConfigChange
from gwadmin.watch.clients.dac_client import ObservedDACStateChange
from gwadmin.watch.widgets.dac_widget_info import DACWidgetConfig
from gwadmin.watch.widgets.dac_widget_info import DACWidgetInfo
from gwsproto.named_types import LayoutLite
from gwsproto.named_types import SnapshotSpaceheat

module_logger = logging.getLogger(__name__)
module_logger.addHandler(TextualHandler())

class Dacs(Widget):
    BINDINGS = [
        ("d", "set_dac", "Set selected DAC"),
    ]

    logger: Logger
    _dacs: dict[str, DACWidgetInfo]

    class DacStateChange(Message):
        def __init__(self, changes: dict[str, ObservedDACStateChange]) -> None:
            self.changes = changes
            super().__init__()

    class ConfigChange(Message):
        def __init__(self, changes: dict[str, DACConfigChange]) -> None:
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

    def __init__(self, logger: Optional[Logger] = None, **kwargs) -> None:
        self.logger = logger or module_logger
        self._dacs = {}
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        with Horizontal(id="dacs_horizontal"):
            yield DataTable(
                id="dacs_table",
                zebra_stripes=True,
                cursor_type="row",
            )
            with Horizontal(id="dac_control_container"):
                with Vertical(id="dac_input_vertical"):
                    yield Static("Value for DAC:  ", id="dacs_input_label")
                    yield Input(
                        type="integer",
                        id="dac_value_input",
                    )
                yield Button(
                    id="send_dac_button",
                    label="Send Value to DAC",
                    variant="primary",
                )

    def on_mount(self) -> None:
        data_table = self.query_one("#dacs_table", DataTable)
        for column_name, width in [
            ("Name", 25),
            ("Current value", 25),
        ]:
            data_table.add_column(column_name, key=column_name, width=width)

    def _get_dac_row_data(self, dac_name: str) -> dict[str, CellType]:
        if dac_name in self._dacs:
            dac = self._dacs[dac_name]
            return {
                "Name": dac.config.table_name.row_name,
                "Current value": dac.config.get_current_state_str(dac.get_state()),
            }
        return {}

    def on_dacs_dac_state_change(self, message: DacStateChange) -> None:
        for dac_name, change in message.changes.items():
            dac_info = self._dacs.get(dac_name, None)
            if dac_info is not None:
                new_state = DACWidgetInfo.get_observed_state(change.new_state)
                if new_state != dac_info.get_state():
                    dac_info.observed = change.new_state
                    self._update_dac_row(dac_name)


    def _get_dac_row(self, dac_name: str) -> list[str | CellType]:
        return list(self._get_dac_row_data(dac_name).values())

    def _update_dac_row(self, dac_name: str) -> None:
        table = self.query_one("#dacs_table", DataTable)
        data = self._get_dac_row_data(dac_name)
        for column_name, value in data.items():
            table.update_cell(
                dac_name,
                column_name,
                value,
                update_width=column_name=="State",
            )

    def on_dacs_config_change(self, message: ConfigChange) -> None:
        message.prevent_default()
        table = self.query_one("#dacs_table", DataTable)
        for dac_name, change in message.changes.items():
            dac_info = self._dacs.get(dac_name, None)
            if dac_info is not None:
                if change.new_config is None:
                    self._dacs.pop(dac_name)
                    table.remove_row(dac_name)
                else:
                    new_config = DACWidgetConfig.from_config(change.new_config)
                    if new_config != dac_info.config:
                        dac_info.config = new_config
                        self._update_dac_row(dac_name)
            else:
                if change.new_config is not None:
                    self._dacs[dac_name] = DACWidgetInfo(
                        config=DACWidgetConfig.from_config(change.new_config)
                    )
                    table.add_row(
                        *self._get_dac_row(dac_name),
                        key=dac_name
                    )
        table.sort("Name")

    def on_data_table_row_highlighted(self, message: DataTable.RowHighlighted) -> None:
        self._update_dac_row(message.row_key.value)

    def dac_client_callbacks(self) -> DACClientCallbacks:
        return DACClientCallbacks(
            mqtt_state_change_callback=None,
            dac_state_change_callback=self.dac_state_change_callback,
            dac_config_change_callback=self.dac_config_change_callback,
            # disable these as defense against memroy leaks
            mqtt_message_received_callback=None,
            layout_callback=None,
            snapshot_callback=None,
        )

    def dac_state_change_callback(self, changes: dict[str, ObservedDACStateChange]) -> None:
        self.post_message(Dacs.DacStateChange(changes))

    def dac_config_change_callback(self, changes: dict[str, DACConfigChange]) -> None:
        self.post_message(Dacs.ConfigChange(changes))

