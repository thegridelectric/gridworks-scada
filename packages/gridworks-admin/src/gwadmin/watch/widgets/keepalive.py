import logging
from textual.logging import TextualHandler
from textual.message import Message
from textual.widgets import Button

from gwadmin.config import DEFAULT_ADMIN_TIMEOUT
from gwadmin.config import MAX_ADMIN_TIMEOUT
from gwadmin.watch.widgets.timer import TimerDigits
from gwadmin.watch.widgets.time_input import TimeInput

module_logger = logging.getLogger(__name__)
module_logger.addHandler(TextualHandler())

class KeepAliveButton(Button):
    def __init__(
            self,
            default_timeout_seconds: int = DEFAULT_ADMIN_TIMEOUT,
            logger: logging.Logger = module_logger,
            **kwargs
    ) -> None:
        super().__init__(
            "Keep alive",
            variant="primary",
            id="keepalive_button",
            **kwargs
        )
        self.logger = logger
        self.default_timeout_seconds = default_timeout_seconds
        self.timeout_seconds = self.default_timeout_seconds

    class Pressed(Message):
        def __init__(self, timeout_seconds):
            self.timeout_seconds = timeout_seconds
            if timeout_seconds > MAX_ADMIN_TIMEOUT:
                self.timeout_seconds = None
            super().__init__()

    def on_button_pressed(self) -> None:
        input_value = self.app.query_one(TimeInput).value
        try:
            if input_value:
                self.timeout_seconds = int(float(input_value)*60)
            else:
                self.timeout_seconds = int(self.default_timeout_seconds)
        except ValueError:
            print(f"Invalid input: '{input_value}', please enter a valid number.")
        self.post_message(KeepAliveButton.Pressed(self.timeout_seconds))
        timer_display = self.app.query_one(TimerDigits)
        timer_display.restart(self.timeout_seconds)


class ReleaseControlButton(Button):
    def __init__(
            self,
            default_timeout_seconds: int = DEFAULT_ADMIN_TIMEOUT,
            logger: logging.Logger = module_logger,
            **kwargs
    ) -> None:
        super().__init__(
            "Release control",
            variant="primary",
            id="release_control_button",
            **kwargs
        )
        self.logger = logger
        self.default_timeout_seconds = default_timeout_seconds
        self.timeout_seconds = self.default_timeout_seconds

    class Pressed(Message):
        ...

    def on_button_pressed(self) -> None:
        timer_display = self.app.query_one(TimerDigits)
        timer_display.reset()
        timer_display.stop()
        self.post_message(
            ReleaseControlButton.Pressed()
        )
