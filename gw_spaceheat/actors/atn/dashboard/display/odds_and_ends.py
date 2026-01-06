from typing import Self

from gwsproto.enums import GwUnit, TelemetryName
from gwsproto.conversions.temperature import convert_temp_to_f
from rich.console import Console
from rich.console import ConsoleOptions
from rich.console import RenderResult
from rich.table import Table

from actors.atn.dashboard.channels.containers import Channels
from actors.atn.dashboard.channels.read_mixin import UnboundReading



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
        self.table.add_column("Unit", header_style="bold green1", style="green1")

        for reading in self.channels.last_unbound_readings:
            value_str, unit_str = self._format_reading(reading)
            self.table.add_row(reading.ChannelName, value_str, unit_str)
        return self

    def _format_reading(self, reading: UnboundReading) -> tuple[str, str]:
        """
        Returns (value_str, unit_str) suitable for display.
        """
        telemetry = getattr(reading, "Telemetry", None)
        unit = getattr(reading, "Unit", None)
        raw = reading.Value
        unit = reading.Unit

        if unit in (
            TelemetryName.AirTempCTimes1000,
            TelemetryName.WaterTempCTimes1000,
            TelemetryName.AirTempFTimes1000,
            TelemetryName.WaterTempFTimes1000,
            GwUnit.FahrenheitX100
        ):
            assert unit
            temp_f = convert_temp_to_f(raw=raw, encoding=unit)
            return f"{temp_f:.2f}", "°F"

        # Fallback: raw display
        return str(raw), str(telemetry or unit or "")

    def __rich_console__(self, _console: Console, _options: ConsoleOptions) -> RenderResult:
        yield self.table
