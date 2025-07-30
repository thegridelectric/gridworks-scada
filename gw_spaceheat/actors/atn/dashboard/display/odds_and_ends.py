from typing import Self

from gwproto.enums import TelemetryName
from rich.console import Console
from rich.console import ConsoleOptions
from rich.console import RenderResult
from rich.table import Table

from actors.atn.dashboard.channels.containers import Channels


class OddsAndEnds:
    table: Table

    def __init__(self, channels: Channels):
        self.channels = channels
        self.update()

    def update(self) -> Self:
        self.table = Table(
            # title="Odds and Ends",
            title_justify="left",
            title_style="bold blue",
        )
        self.table.add_column("Channel", header_style="bold green", style="green")
        self.table.add_column("Value", header_style="bold dark_orange", style="dark_orange")
        self.table.add_column("Telemetry", header_style="bold green1", style="green1")
        for reading in self.channels.last_unused_readings:
            if reading.Telemetry in (
                    TelemetryName.WaterTempCTimes1000,
                    TelemetryName.AirTempCTimes1000
            ):
                value_str = f"{round((reading.Value / 1000 * 9 / 5) + 32, 2)}"
                telemetry_str = "\u00b0F"
            elif reading.Telemetry in (
                    TelemetryName.WaterTempFTimes1000,
                    TelemetryName.AirTempFTimes1000
            ):
                value_str = f"{round(reading.Value / 1000, 2)}"
                telemetry_str = "\u00b0F"
            else:
                value_str = str(reading.Value)
                telemetry_str = str(reading.Telemetry)
            self.table.add_row(reading.ChannelName, value_str, telemetry_str)
        return self

    def __rich_console__(self, _console: Console, _options: ConsoleOptions) -> RenderResult:
        yield self.table
