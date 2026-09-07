import logging
from textual.logging import TextualHandler
from textual.message import Message
from textual.widgets import Button

from gwadmin.config import DEFAULT_ADMIN_TIMEOUT
from gwadmin.watch.widgets.timer import TimerDigits
from gwadmin.watch.widgets.time_input import TimeInput

module_logger = logging.getLogger(__name__)
module_logger.addHandler(TextualHandler())


class RebootPicosButton(Button, can_focus=True):
    """Asks the pico-cycler to power-cycle the picos, keeping admin alive for
    the timeout in the time input like a relay toggle does."""

    BINDINGS = [
        ("p", "reboot_picos", "Reboot picos"),
    ]

    def __init__(
            self,
            default_timeout_seconds: int = DEFAULT_ADMIN_TIMEOUT,
            logger: logging.Logger = module_logger,
            **kwargs
    ) -> None:
        super().__init__(
            "Reboot [underline]p[/]icos",
            variant="warning",
            id="reboot_picos_button",
            **kwargs
        )
        self.logger = logger
        self.default_timeout_seconds = default_timeout_seconds
        self.timeout_seconds = self.default_timeout_seconds

    class Pressed(Message):
        def __init__(self, timeout_seconds: int) -> None:
            self.timeout_seconds = timeout_seconds
            super().__init__()

    def action_reboot_picos(self) -> None:
        self.on_button_pressed()

    def on_button_pressed(self) -> None:
        input_value = self.app.query_one(TimeInput).value
        try:
            time_in_minutes = float(input_value) if input_value else int(self.default_timeout_seconds / 60)
            self.timeout_seconds = int(time_in_minutes * 60)
        except ValueError:
            self.timeout_seconds = self.default_timeout_seconds
        self.post_message(RebootPicosButton.Pressed(self.timeout_seconds))
        timer_display = self.app.query_one(TimerDigits)
        timer_display.restart(self.timeout_seconds)
