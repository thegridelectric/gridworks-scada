from textual.widgets import Input
from textual.validation import Number

from gwadmin.config import DEFAULT_ADMIN_TIMEOUT


class TimeInput(Input):
    def __init__(self, default_timeout_seconds: int = DEFAULT_ADMIN_TIMEOUT, **kwargs):
        default_value = int(default_timeout_seconds/60)
        super().__init__(
            placeholder=f"Timeout minutes (default {default_value})",
            id="time_input",
            validators=[Number(minimum=1, maximum=24*60)],
            **kwargs
        )