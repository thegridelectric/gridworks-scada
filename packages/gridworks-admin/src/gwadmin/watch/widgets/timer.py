import logging
from time import monotonic
from textual.logging import TextualHandler
from textual.timer import Timer
from textual.widgets import Digits
from textual.reactive import reactive

from gwadmin.config import DEFAULT_ADMIN_TIMEOUT
from gwadmin.config import MAX_ADMIN_TIMEOUT
from gwadmin.watch.widgets.time_input import TimeInput

module_logger = logging.getLogger(__name__)
module_logger.addHandler(TextualHandler())

class TimerDigits(Digits):
    update_timer: Timer
    start_time = reactive(monotonic)
    time_remaining = reactive(DEFAULT_ADMIN_TIMEOUT)

    def __init__(
            self,
            default_timeout_seconds: int = DEFAULT_ADMIN_TIMEOUT,
            logger: logging.Logger = module_logger,
            **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.logger = logger
        self.default_timeout_seconds = default_timeout_seconds
        self.countdown_seconds = self.default_timeout_seconds


    def on_mount(self) -> None:
        self.update_timer = self.set_interval(1 / 60, self.update_time, pause=True)

    def update_time(self) -> None:
        elapsed = monotonic() - self.start_time
        self.time_remaining = max(0.0, self.countdown_seconds - elapsed)
        
        if self.time_remaining <= 0:
            self.stop()

    def watch_time_remaining(self, time: float) -> None:
        minutes, seconds = divmod(time, 60)
        hours, minutes = divmod(minutes, 60)
        self.update(f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}")

    def start(self, timeout_seconds: int) -> None:
        self.countdown_seconds = timeout_seconds
        self.time_remaining = self.countdown_seconds
        self.start_time = monotonic()
        self.update_timer.resume()

    def stop(self) -> None:
        self.update_timer.pause()

    def reset(self) -> None:
        input_value = self.app.query_one(TimeInput).value
        try:
            time_in_minutes = float(input_value) if input_value else int(self.default_timeout_seconds/60)
            if time_in_minutes > int(MAX_ADMIN_TIMEOUT/60):
                time_in_minutes = int(MAX_ADMIN_TIMEOUT/60)
        except ValueError:
            time_in_minutes = int(self.default_timeout_seconds/60)
        self.time_remaining = time_in_minutes * 60

    def restart(self, timeout_seconds) -> None:
        self.reset()
        self.start(timeout_seconds)