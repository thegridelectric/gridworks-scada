import logging

import dotenv
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.logging import TextualHandler
from textual.widgets import Header, Footer

from gwadmin.settings import MAX_ADMIN_TIMEOUT
from gwadmin.watch.clients.admin_client import AdminClient
from gwadmin.watch.clients.relay_client import RelayEnergized
from gwadmin.watch.clients.relay_client import RelayWatchClient
from gwadmin.watch.widgets.keepalive import KeepAliveButton
from gwadmin.watch.widgets.keepalive import ReleaseControlButton
from gwadmin.watch.widgets.relays import Relays
from gwadmin.watch.widgets.relay_toggle_button import RelayToggleButton
from gwadmin.watch.widgets.timer import TimerDigits
from gwadmin.settings import AdminClientSettings

__version__: str = "0.2.4"

logger = logging.getLogger(__name__)
logger.addHandler(TextualHandler())


class RelaysApp(App):
    TITLE: str = f"Scada Relay Monitor v{__version__}"
    _admin_client: AdminClient
    _relay_client: RelayWatchClient
    _theme_names: list[str]

    BINDINGS = [
        Binding("d", "toggle_dark", "Toggle dark mode"),
        Binding("[", "previous_theme", " <- Theme ->"),
        Binding("]", "next_theme", " "),
        # Binding("m", "toggle_messages", "Toggle message display"),
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]
    CSS_PATH = "relay_app.tcss"

    def __init__(
        self,
        *,
        settings: AdminClientSettings = AdminClientSettings(),
    ) -> None:
        self.settings = settings
        logger.setLevel(settings.verbosity)
        if self.settings.paho_verbosity is not None:
            paho_logger = logging.getLogger("paho." + __name__)
            paho_logger.addHandler(TextualHandler())
            paho_logger.setLevel(settings.paho_verbosity)
        else:
            paho_logger = None
        self._relay_client = RelayWatchClient(logger=logger)
        self._admin_client = AdminClient(
            settings,
            subclients=[self._relay_client],
            logger=logger,
            paho_logger=paho_logger,
        )
        super().__init__()
        self._theme_names = [
            theme for theme in self.available_themes if theme != "textual-ansi"
        ]
        self.set_reactive(RelaysApp.sub_title, self.settings.target_gnode)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=self.settings.show_clock)
        relays = Relays(logger=logger, id="relays")
        self._relay_client.set_callbacks(relays.relay_client_callbacks())
        yield relays
        # Footer disabled by default as defense against memory leaks
        if self.settings.show_footer:
            yield Footer()

    def on_mount(self) -> None:
        self._admin_client.start()

    def on_relay_toggle_button_pressed(self, message: RelayToggleButton.Pressed):
        self._relay_client.set_relay(
            message.about_node_name,
            RelayEnergized.energized if message.energize else RelayEnergized.deenergized,
            message.timeout_seconds
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

    # def action_toggle_messages(self) -> None:
    #     self.query("#message_table").toggle_class("undisplayed")

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

if __name__ == "__main__":
    # https://github.com/koxudaxi/pydantic-pycharm-plugin/issues/1013
    # noinspection PyArgumentList
    settings_ = AdminClientSettings(_env_file=dotenv.find_dotenv())
    settings_.verbosity = logging.DEBUG
    # settings_.paho_verbosity = logging.DEBUG
    app = RelaysApp(settings=settings_)
    app.run()
