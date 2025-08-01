from rich.console import Console
from rich.console import ConsoleOptions
from rich.console import RenderResult
from rich.text import Text

class BaseReading:
    text: Text

    def __init__(self, text: Text | str = "") -> None:
        if isinstance(text, str):
            text = Text(text)
        self.text = text

    def __str__(self):
        return str(self.text.markup)

    def __rich_console__(self, _console: Console, _options: ConsoleOptions) -> RenderResult:
        yield self.text.markup

    def __bool__(self) -> bool:
        return False

class MissingReading(BaseReading): ...

class Reading(BaseReading):
    raw: int
    converted: float | int
    report_time_unix_ms: int
    idx: int

    def __init__(
        self,
        *,
        raw: int,
        converted: float | int,
        report_time_unix_ms: int,
        idx: int,
        text: Text | str,
    ):
        super().__init__(text=text)
        self.raw = raw
        self.converted = converted
        self.report_time_unix_ms = report_time_unix_ms
        self.idx = idx

    def __bool__(self) -> bool:
        return True
