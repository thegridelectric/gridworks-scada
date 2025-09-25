import importlib.metadata
import logging

import dotenv
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.containers import HorizontalGroup
from textual.logging import TextualHandler
from textual.widgets import Button
from textual.widgets import DataTable
from textual.widgets import Header, Footer
from textual.widgets import Input
from textual.widgets import Select
from textual.widgets import Static

from gwadmin.config import CurrentAdminConfig
from gwadmin.config import MAX_ADMIN_TIMEOUT
from gwadmin.watch.clients.admin_client import AdminClient
from gwadmin.watch.clients.dac_client import DACWatchClient
from gwadmin.watch.clients.relay_client import RelayEnergized
from gwadmin.watch.clients.relay_client import RelayWatchClient
from gwadmin.watch.widgets.dacs import Dacs
from gwadmin.watch.widgets.keepalive import KeepAliveButton
from gwadmin.watch.widgets.keepalive import ReleaseControlButton
from gwadmin.watch.widgets.mqtt import MqttState
from gwadmin.watch.widgets.relays import Relays
from gwadmin.watch.widgets.relay_toggle_button import RelayToggleButton
from gwadmin.watch.widgets.time_input import TimeInput
from gwadmin.watch.widgets.timer import TimerDigits

__version__: str = importlib.metadata.version('gridworks-admin')

logger = logging.getLogger(__name__)
logger.addHandler(TextualHandler())


class RelaysApp(App):
    TITLE: str = f"Scada Relay Monitor v{__version__}"
    _admin_client: AdminClient
    _relay_client: RelayWatchClient
    _dac_client: DACWatchClient
    _theme_names: list[str]
    settings: CurrentAdminConfig

    BINDINGS = [
        Binding("r", "focus('relays_table')", "Select relays"),
        Binding("d", "focus('dacs_table')", "Select DACs"),
        Binding("k", "toggle_dark", "Toggle dark mode"),
        Binding("[", "previous_theme", " <- Theme ->"),
        Binding("]", "next_theme", " "),
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]
    CSS_PATH = "relay_app.tcss"

    def __init__(
        self,
        *,
        settings: CurrentAdminConfig = CurrentAdminConfig(),
    ) -> None:
        self.settings = settings
        logger.setLevel(settings.config.verbosity)
        if self.settings.config.paho_verbosity is not None:
            paho_logger = logging.getLogger("paho." + __name__)
            paho_logger.addHandler(TextualHandler())
            paho_logger.setLevel(settings.config.paho_verbosity)
        else:
            paho_logger = None
        self._relay_client = RelayWatchClient(logger=logger)
        self._dac_client = DACWatchClient(logger=logger)
        self._admin_client = AdminClient(
            settings,
            subclients=[self._relay_client, self._dac_client],
            logger=logger,
            paho_logger=paho_logger,
        )
        super().__init__()
        self._theme_names = [
            theme for theme in self.available_themes if theme != "textual-ansi"
        ]
        self.set_reactive(RelaysApp.sub_title, self.format_sub_title())

    def format_sub_title(self) -> str:
        return f"{self.settings.curr_scada} - {self.settings.config.scadas[self.settings.curr_scada].long_name}"

    def compose(self) -> ComposeResult:
        if self.settings.config.show_selected_scada_block:
            selected_scada_block_classes = ""
        else:
            selected_scada_block_classes = "undisplayed"
        yield Header(show_clock=self.settings.config.show_clock)
        yield Horizontal(
            Static(
                "Selected scada:",
                id="select_scada_label"),
                Select(
                    (
                        (scada, scada) for scada in [
                            scada_name
                            for scada_name, scada_config in self.settings.config.scadas.items()
                            if scada_config.enabled
                        ]
                    ),
                    value=self.settings.curr_scada,
                    id="select_scada",
                    allow_blank=False,
                ),
                MqttState(id="mqtt_state"),
                Static(
                    self.settings.curr_scada,
                    id="selected_scada_label",
                    classes=selected_scada_block_classes,
                ),
            id="select_scada_container",
            classes="section"
        )
        with HorizontalGroup(id="timer_container", classes="section"):
            timeout = self.settings.config.default_timeout_seconds
            yield KeepAliveButton(default_timeout_seconds=timeout)
            yield ReleaseControlButton(
                default_timeout_seconds=timeout
            )
            yield TimeInput(default_timeout_seconds=timeout)
            yield TimerDigits(default_timeout_seconds=timeout)
        relays = Relays(
            scadas=[
                scada_name
                for scada_name, scada_config in self.settings.config.scadas.items()
                if scada_config.enabled
            ],
            initial_scada=self.settings.curr_scada,
            default_timeout_seconds=self.settings.config.default_timeout_seconds,
            logger=logger,
            id="relays",
            classes="section",
        )
        relays.border_title = "Relays"
        yield relays
        self._relay_client.set_callbacks(relays.relay_client_callbacks())
        dacs = Dacs(logger=logger, id="dacs", classes="section")
        self._dac_client.set_callbacks(dacs.dac_client_callbacks())
        yield dacs
        # Footer disabled by default as defense against memory leaks
        if self.settings.config.show_footer:
            yield Footer()

    def on_mount(self) -> None:
        self._admin_client.start()

    def on_relay_toggle_button_pressed(self, message: RelayToggleButton.Pressed):
        self._relay_client.set_relay(
            message.about_node_name,
            RelayEnergized.energized if message.energize else RelayEnergized.deenergized,
            message.timeout_seconds
        )

    @on(Button.Pressed, "#send_dac_button")
    def send_dac_button(self) -> None:
        new_state = self.query_one("#dac_value_input", Input).value
        if new_state is not None:
            new_state = int(new_state)
            dac_table = self.query_one("#dacs_table", DataTable)
            row = dac_table.get_row_at(dac_table.cursor_row)
            time_input_value = self.app.query_one(TimeInput).value
            try:
                time_in_minutes = float(time_input_value) if time_input_value else int(self.settings.config.default_timeout_seconds/60)
                timeout_seconds = int(time_in_minutes * 60)
            except:  # noqa
                timeout_seconds = self.settings.config.default_timeout_seconds
            self._dac_client.set_dac(
                dac_row_name=row[0],
                new_state=new_state,
                timeout_seconds=timeout_seconds,
            )

    def action_toggle_dark(self) -> None:
        self.theme = (
            "textual-dark" if "light" in self.theme else "textual-light"
        )
        self.clear_notifications()
        self.notify(f"Theme is {self.current_theme.name}")

    async def action_quit(self) -> None:
        self._admin_client.stop()
        await super().action_quit()

    def _change_theme(self, distance: int):
        self.theme = self._theme_names[
            (self._theme_names.index(self.current_theme.name) + distance)
            % len(self._theme_names)
        ]
        self.clear_notifications()
        self.notify(f"Theme is {self.current_theme.name}")

    def action_next_theme(self) -> None:
        self._change_theme(1)

    def action_previous_theme(self) -> None:
        self._change_theme(-1)

    def on_keep_alive_button_pressed(self, _: KeepAliveButton.Pressed):
        if _.timeout_seconds is not None:
            self.notify(f"Keeping admin alive for {int(_.timeout_seconds/60)} minutes")
            self._relay_client.send_keepalive(_.timeout_seconds)
        else:
            self.notify(f"Keeping admin alive for maximum timeout ({int(MAX_ADMIN_TIMEOUT/60)} min)")
            self._relay_client.send_keepalive(_.timeout_seconds)
            timer_display = self.app.query_one(TimerDigits)
            timer_display.restart(MAX_ADMIN_TIMEOUT)

    def on_release_control_button_pressed(self, _: ReleaseControlButton.Pressed):
        self._relay_client.send_release_control()

    def layout_received(self) -> bool:
        return self._admin_client.layout_received()

    def snapshot_received(self) -> bool:
        return self._admin_client.snapshot_received()

    def on_select_changed(self, message: Select.Changed) -> None:
        if message.value != Select.BLANK and message.value != self.settings.curr_scada:
            self.settings.curr_scada = message.value
            if self.settings.config.use_last_scada:
                self.settings.save_curr_scada(self.settings.curr_scada)
            self.sub_title = self.format_sub_title()
            self.query_one("#selected_scada_label", Static).content = self.settings.curr_scada
            self._admin_client.switch_scada()


if __name__ == "__main__":
    from gwadmin.cli import get_admin_config
    settings_ = get_admin_config(env_file=dotenv.find_dotenv())
    settings_.config.verbosity = logging.DEBUG
    app = RelaysApp(settings=settings_)
    app.run()
