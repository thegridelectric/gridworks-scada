import logging

import dotenv
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer
from textual.widgets import Header
from textual.widgets import Static

from gwadmin.settings import AdminClientSettings


class WatchExApp(App):
    settings: AdminClientSettings

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    CSS_PATH = "watchex_app.tcss"

    def __init__(
        self,
        *,
        settings: AdminClientSettings = AdminClientSettings(),
    ) -> None:
        self.settings = settings
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            (
                "There is no extended functionality at this time.\n\n"
                "Use 'gws admin watch'\n\n"
                "Press 'q' to quit"
            )
        )
        yield Footer()

if __name__ == "__main__":
    # https://github.com/koxudaxi/pydantic-pycharm-plugin/issues/1013
    # noinspection PyArgumentList
    settings_ = AdminClientSettings(_env_file=dotenv.find_dotenv())
    settings_.verbosity = logging.DEBUG
    # settings_.paho_verbosity = logging.DEBUG
    app = WatchExApp(settings=settings_)
    app.run()
