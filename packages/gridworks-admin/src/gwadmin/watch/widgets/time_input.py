from textual.widgets import Input
from textual.validation import Number
from gwadmin.settings import AdminClientSettings

class TimeInput(Input):
    def __init__(self, **kwargs):
        default_value = int(AdminClientSettings().default_timeout_seconds/60)
        super().__init__(
            placeholder=f"Timeout minutes (default {default_value})",
            id="time_input",
            validators=[Number(minimum=1, maximum=24*60)],
            **kwargs
        )