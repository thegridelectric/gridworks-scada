from datetime import datetime
from typing import Deque
from typing import Self

from rich.console import Console
from rich.console import ConsoleOptions
from rich.console import RenderResult
from rich.table import Table

from tests.atn.dashboard.channels.containers import Channels
from tests.atn.dashboard.display.styles import none_text
from tests.atn.dashboard.hackhp import HackHpState
from tests.atn.dashboard.hackhp import HackHpStateCapture


class PowerDisplay:
    table: Table
    hack_hp_state_q: Deque[HackHpStateCapture]

    def __init__(self, channels: Channels, hack_hp_state_q: Deque[HackHpStateCapture]) -> None:
        self.channels = channels
        self.hack_hp_state_q = hack_hp_state_q
        self.update()

    def update(self) -> Self:
        self.table = Table()

        self.table.add_column("HP Power", header_style="bold")
        self.table.add_column("kW", header_style="bold")
        self.table.add_column(
            "X",
            header_style="bold dark_orange",
            style="dark_orange"
        )
        self.table.add_column("Pump", header_style="bold")
        self.table.add_column("Gpm", header_style="bold")
        self.table.add_column("Pwr (W)", header_style="bold")
        self.table.add_column(
            "HP State",
            header_style="bold dark_orange",
            style="bold dark_orange"
        )
        extra_cols = min(len(self.hack_hp_state_q), 5)
        for i in range(extra_cols):
            self.table.add_column(
                f"{self.hack_hp_state_q[i].state.value}",
                header_style="bold"
            )

        hp_pwr_w_str = f"{round(self.hack_hp_state_q[0].hp_pwr_w / 1000, 2)}"
        if self.hack_hp_state_q[0].idu_pwr_w is None:
            idu_pwr_w_str = none_text
            odu_pwr_w_str = none_text
        else:
            idu_pwr_w_str = f"{round(self.hack_hp_state_q[0].idu_pwr_w / 1000, 2)}"
            odu_pwr_w_str = f"{round(self.hack_hp_state_q[0].odu_pwr_w / 1000, 2)}"

        row_1 = [
            "Hp Total", hp_pwr_w_str,
            "x",
            "Primary", str(self.channels.flows.primary_flow),
            str(self.channels.power.pumps.primary),
            "Started"
        ]
        row_2 = [
            "Outdoor", odu_pwr_w_str,
            "x",
            "Dist", str(self.channels.flows.dist_flow),
            str(self.channels.power.pumps.dist),
            "Tries"
        ]
        row_3 = [
            "Indoor", idu_pwr_w_str,
            "x",
            "Store", str(self.channels.flows.store_flow),
            str(self.channels.power.pumps.store),
            "PumpPwr"
        ]
        for i in range(extra_cols):
            row_1.append(
                datetime.fromtimestamp(
                    self.hack_hp_state_q[i].state_start_s
                ).strftime("%H:%M")
            )
            if (self.hack_hp_state_q[i].state == HackHpState.Idling
                    or self.hack_hp_state_q[i].state == HackHpState.Trying):
                row_2.append(f"{self.hack_hp_state_q[i].start_attempts}")
            else:
                row_2.append(f"")
            row_3.append(f"{self.hack_hp_state_q[i].primary_pump_pwr_w} W")

        self.table.add_row(*row_1)
        self.table.add_row(*row_2)
        self.table.add_row(*row_3)
        return self

    def __rich_console__(self, _console: Console, _options: ConsoleOptions) -> RenderResult:
        yield self.table
