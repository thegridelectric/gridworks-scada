from datetime import datetime
from typing import Deque
from typing import Self

from rich.console import Console
from rich.console import ConsoleOptions
from rich.console import RenderResult
from rich.style import Style
from rich.text import Text

from actors.atn.dashboard.display.styles import temperature_markup
from actors.atn.dashboard.channels.channel import TemperatureChannel
from actors.atn.dashboard.display.styles import misc_style
from actors.atn.dashboard.display.styles import cold_style
from actors.atn.dashboard.display.styles import hot_style
from actors.atn.dashboard.hackhp import HackHpState
from actors.atn.dashboard.hackhp import HackHpStateCapture
from actors.atn.dashboard.channels.containers import Channels

class PipePair:
    hot: str
    cold: str
    hot_title: str
    cold_title: str

    def __init__(
            self,
            hot_channel: TemperatureChannel,
            cold_channel: TemperatureChannel,
            hot_title: str,
            cold_title: str,
    ) -> None:
        pair_hot_style, pair_cold_style = self.hot_cold_styles(
            hot_channel,
            cold_channel,
        )
        self.hot_title = Text(hot_title, style=pair_hot_style).markup
        self.cold_title = Text(cold_title, style=pair_cold_style).markup
        self.hot = temperature_markup(hot_channel.converted, pair_hot_style)
        self.cold = temperature_markup(cold_channel.converted, pair_cold_style)

    @classmethod
    def hot_cold_styles(
            cls,
            hot_channel: TemperatureChannel,
            cold_channel: TemperatureChannel
    ) -> tuple[Style, Style]:
        hot_f = hot_channel.converted
        cold_f = cold_channel.converted
        if hot_f is not None and cold_f is not None and hot_f < cold_f - 1:
            return cold_style, hot_style
        return hot_style, cold_style


class AsciiPicture:
    short_name: str
    channels: Channels
    ascii_picture: str
    print_hack_hp: bool

    def __init__(
        self,
        short_name: str,
        channels: Channels,
        *,
        print_hack_hp: bool,
        hack_hp_state_q: Deque[HackHpStateCapture]
    ):
        self.short_name = short_name
        self.channels = channels
        self.print_hack_hp = print_hack_hp
        self.hack_hp_state_q = hack_hp_state_q
        self.ascii_picture = ""

    def update(self) -> Self:
        temperatures = self.channels.temperatures
        hp = PipePair(
            temperatures.hp_lwt, temperatures.hp_ewt,
            "HP LWT", "HP EWT",
        )
        dist = PipePair(
            temperatures.dist_swt, temperatures.dist_rwt,
            "Dist SWT", "Dist RWT"
        )
        buff = PipePair(
            temperatures.buffer_hot_pipe, temperatures.buffer_cold_pipe,
            "Buff Hot", "Buff Cold"
        )
        store = PipePair(
            temperatures.store_hot_pipe, temperatures.store_cold_pipe,
            "", ""
        )
        lift = self._temp_diff("hp_lwt", "hp_ewt")
        emitter = self._temp_diff("dist_swt", "dist_rwt")
        hp_health_1, hp_health_2 = self._hp_hack_comments()
        tanks = temperatures.tanks
        buffer = tanks.buffer
        store1 = tanks.store[0]
        store2 = tanks.store[1]
        store3 = tanks.store[2]
        self.ascii_picture = f"""
                                 {hp.hot_title}   ┏━━━━━┓   {hp_health_1}
                               ┏━{hp.hot}━━┃ HP  ┃   {hp_health_2}
  {buff.hot_title} ━━┓                 ┃    ┏─────┃     ┃   Lift: {lift}
   {buff.hot}   ┃                 ┃ {hp.cold_title}   └─────┘
 ┏━━━━━━━━━┓ ▼                 ┃ {hp.cold}
 ┃  Buffer ┃━━━━━━━━━┳━ ISO ━━─┴─━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
 ┡━━━━━━━━━┩         ┃              │         ┏━━━━━━━━━┓   ┏━━━━━━━━━┓   ┏━━━━━━━━━┓    ┃
 │ {buffer.depth1} │       {dist.hot_title}         │         ┃  Tank3  ┃   ┃  Tank2  ┃   ┃  Tank1  ┃    ┃
 │ {buffer.depth2} │       {dist.hot}          │         ┡━━━━━━━━━┩━┓ ┡━━━━━━━━━┩━┓ ┡━━━━━━━━━┩━━━{store.hot}
 │ {buffer.depth3} │         ┃              │         │ {store3.depth1} │ │ │ {store2.depth1} │ │ │ {store1.depth1} │
 │ {buffer.depth4} │────┓    ┃              │         │ {store3.depth2} │ │ │ {store2.depth2} │ │ │ {store1.depth2} │
 └─────────┘ ▲  │    ┃              │         │ {store3.depth3} │ │ │ {store2.depth3} │ │ │ {store1.depth3} │
  {buff.cold_title}  │  ┡────┃──────────────┴─{store.cold}─│ {store3.depth4} │ └━│ {store2.depth4} │ └━│ {store1.depth4} │
   {buff.cold} ──┘  │    ┃                        └─────────┘   └─────────┘   └─────────┘
            {dist.cold_title} ┃
            {dist.cold}  ┃  Emitter Δ = {emitter}
                │    ┃
                └⏴🏠⏴┛
"""

        return self

    def _hot_cold_styles(self, hot:str, cold: str) -> tuple[Style, Style]:
        hot_f = getattr(self.channels.temperatures, hot).converted
        cold_f = getattr(self.channels.temperatures, cold).converted
        if hot_f is not None and cold_f is not None and hot_f < cold_f - 1:
            return cold_style, hot_style
        return hot_style, cold_style

    def _temp_diff(self, hot:str, cold:str, style: Style | str = misc_style) -> str:
        hot_f = getattr(self.channels.temperatures, hot).converted
        cold_f = getattr(self.channels.temperatures, cold).converted
        if hot_f is not None and cold_f is not None:
            return temperature_markup(round(hot_f - cold_f, 1), style_calculator=style)
        return " --- "

    def _hp_hack_comments(self) -> tuple[str, str]:
        hp_health_comment_1 = hp_health_comment_2 = ""
        if self.print_hack_hp:
            hack_hp_state = self.hack_hp_state_q[0]
            if hack_hp_state.state == HackHpState.Heating:
                heating = True
            else:
                heating = False
            if heating is True:
                hp_health_comment_1 = ""
                hp_health_comment_2 = ""
            else:
                hp_health_comment_1 = f"{hack_hp_state.state.value}."
                last_heating = next((x for x in self.hack_hp_state_q if x.state == HackHpState.Heating), None)
                hp_health_comment_2 = ""
                if last_heating is not None:
                    if last_heating.state_end_s:
                        hp_health_comment_2 += f"Last time heating: {datetime.fromtimestamp(last_heating.state_end_s).strftime('%H:%M')}. "
                if hack_hp_state.start_attempts == 1:
                    hp_health_comment_2 += "1 start attempt."
                elif hack_hp_state.start_attempts > 1:
                    hp_health_comment_2 += f"{hack_hp_state.start_attempts} start attempts."
        return hp_health_comment_1, hp_health_comment_2

    def __rich_console__(self, _console: Console, _options: ConsoleOptions) -> RenderResult:
        yield self.ascii_picture

