import logging
from typing import Literal
from typing import Optional

from textual.logging import TextualHandler
from textual.message import Message
from textual.reactive import Reactive
from textual.reactive import reactive
from textual.widgets import Button

from gwadmin.config import DEFAULT_ADMIN_TIMEOUT
from gwadmin.watch.widgets.relay_widget_info import RelayWidgetConfig
from gwadmin.watch.widgets.timer import TimerDigits
from gwadmin.watch.widgets.time_input import TimeInput
from gwadmin.watch.widgets.keepalive import KeepAliveButton

module_logger = logging.getLogger(__name__)
module_logger.addHandler(TextualHandler())


class RelayToggleButton(Button, can_focus=True):
    BINDINGS = [
        ("n", "toggle_relay", "Toggle selected relay"),
    ]

    energized: Reactive[Optional[bool]] = reactive(None)
    config: Reactive[RelayWidgetConfig] = reactive(RelayWidgetConfig)
    timeout_seconds: int

    def __init__(
        self,
        energized: Optional[bool] = None,
        config: Optional[RelayWidgetConfig] = None,
        default_timeout_seconds: int = DEFAULT_ADMIN_TIMEOUT,
        logger: logging.Logger = module_logger,
        **kwargs
    ) -> None:
        self.logger = logger
        super().__init__(
            variant=self.variant_from_state(energized),
            **kwargs
        )
        self.default_timeout_seconds = default_timeout_seconds
        self.set_reactive(RelayToggleButton.energized, energized)
        self.set_reactive(RelayToggleButton.config, config or RelayWidgetConfig())
        self.update_title()

    def update_title(self):
        if self.energized is True:
            self.border_title = f"Dee[underline]n[/]ergize"
        elif self.energized is False:
            self.border_title = f"E[underline]n[/]ergize"

    @classmethod
    def variant_from_state(cls, energized: Optional[bool]) -> Literal["default", "success", "error"]:
        if energized is None:
            return "default"
        elif energized:
            return "success"
        return "error"

    def action_toggle_relay(self) -> None:
        input_value = self.app.query_one(TimeInput).value
        try:
            time_in_minutes = float(input_value) if input_value else int(self.default_timeout_seconds/60)
            self.timeout_seconds = int(time_in_minutes * 60)
        except: # noqa
            self.timeout_seconds = self.default_timeout_seconds
        if self.energized is not None:
            self.post_message(
                RelayToggleButton.Pressed(
                    self.config.about_node_name,
                    not self.energized,
                    self.timeout_seconds
                )
            )

    def watch_energized(self) -> None:
        self.label = self.config.get_state_str(not self.energized)
        self.disabled = self.energized is None
        self.variant = self.variant_from_state(self.energized)
        self.update_title()

    def watch_config(self):
        self.label = self.config.get_state_str(not self.energized)
        self.update_title()

    class Pressed(Message):
        def __init__(self, about_node_name: str, energize: bool, timeout_seconds: int) -> None:
            super().__init__()
            self.about_node_name = about_node_name
            self.energize = energize
            self.timeout_seconds = timeout_seconds

    def on_button_pressed(self):
        input_value = self.app.query_one(TimeInput).value
        try:
            time_in_minutes = float(input_value) if input_value else int(self.default_timeout_seconds/60)
            self.timeout_seconds = int(time_in_minutes * 60)
        except:  # noqa
            self.timeout_seconds = self.default_timeout_seconds
        if self.energized is not None:
            self.post_message(
                RelayToggleButton.Pressed(
                    self.config.about_node_name,
                    not self.energized,
                    self.timeout_seconds
                )
            )
        self.post_message(KeepAliveButton.Pressed(self.timeout_seconds))
        timer_display = self.app.query_one(TimerDigits)
        timer_display.restart(self.timeout_seconds)
