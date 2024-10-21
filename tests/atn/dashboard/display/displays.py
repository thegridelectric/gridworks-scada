from datetime import datetime
from typing import Deque
from typing import Self

from rich.console import Console
from rich.console import ConsoleOptions
from rich.console import RenderResult
from rich.style import Style
from rich.text import Text
from textual.messages import Layout

from tests.atn.dashboard.misc import UpdateSources
from tests.atn.atn_config import DashboardSettings
from tests.atn.dashboard.display.odds_and_ends import OddsAndEnds
from tests.atn.dashboard.display.power import PowerDisplay
from tests.atn.dashboard.display.thermostats import ThermostatDisplay
from tests.atn.dashboard.display.picture import AsciiPicture
from tests.atn.dashboard.channels.containers import Channels
from tests.atn.dashboard.hackhp import HackHpStateCapture

class Displays:
    short_name: str
    title: Text
    odds_and_ends: OddsAndEnds
    thermostat: ThermostatDisplay
    power: PowerDisplay
    picture: AsciiPicture
    layout: Layout

    def __init__(
            self,
            settings: DashboardSettings,
            short_name: str,
            channels: Channels,
            hack_hp_state_q: Deque[HackHpStateCapture]
    ) -> None:
        self.short_name = short_name
        self.title = Text()
        self.odds_and_ends = OddsAndEnds(channels)
        self.thermostat = ThermostatDisplay(channels)
        self.power = PowerDisplay(
            channels,
            print_hack_hp=settings.print_hack_hp,
            hack_hp_state_q=hack_hp_state_q,
        )
        self.picture = AsciiPicture(
            short_name,
            channels,
            print_hack_hp=settings.print_hack_hp,
            hack_hp_state_q=hack_hp_state_q,
        )
        self.update(UpdateSources.Initialization, int(datetime.now().timestamp()))

    def update_title(self, update_source: UpdateSources, report_time_s: int) -> Self:
        report_dt = datetime.fromtimestamp(report_time_s)
        self.title = Text.assemble(
            Text(
                self.short_name.capitalize(),
                style=Style(bold=True, color="hot_pink")
            ),
            "   ",
            Text(str(report_dt.strftime('%Y-%m-%d %H:%M:%S')), style="cyan1"),
            "   (",
            Text(update_source, style="orange1"),
            ")",
        )
        return self

    def update(self, update_source: UpdateSources, report_time_s: int) -> Self:
        self.update_title(update_source, report_time_s)
        self.odds_and_ends.update()
        self.thermostat.update()
        self.power.update()
        self.picture.update()
        self.layout = Layout(

        )
        return self

    def __rich_console__(self, _console: Console, _options: ConsoleOptions) -> RenderResult:
        yield Text(
            "\n++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++",
            style=Style(color="yellow1", bold=True),
        )
        yield Text("++", style=Style(color="yellow1", bold=True), end="")
        yield self.title
        yield self.odds_and_ends
        yield self.thermostat
        yield self.power
        yield self.picture
        yield "\n"
        yield Text("--", style=Style(color="yellow1", bold=True), end="")
        yield self.title
        yield Text(
            "--------------------------------------------------------------------------",
            style=Style(color="yellow1", bold=True),
        )


