import logging
from typing import Callable

from typing import Optional

from gwsproto.data_classes.data_channel import DataChannel
from gwsproto.data_classes.derived_channel import DerivedChannel
from gwsproto.enums import TelemetryName, GwUnit
from rich.console import Console
from rich.console import ConsoleOptions
from rich.console import RenderResult
from rich.style import Style
from rich.text import Text

from actors.honeywell_thermostat import HoneywellThermostatOperatingState
from gwsproto.conversions.temperature import convert_temp_to_f
from gwsproto.named_types import SnapshotSpaceheat
from gwsproto.data_classes.hardware_layout import ChannelRegistry
from actors.atn.dashboard.display.styles import fahrenheit_style
from actors.atn.dashboard.display.styles import tank_style
from actors.atn.dashboard.channels.reading import MissingReading
from actors.atn.dashboard.channels.reading import Reading

PUMP_OFF_THRESHOLD = 2

DEFAULT_MISSING_STRING = " --- "
DEFAULT_FORMAT_STRING = "{converted:5.1f}"
DEFAULT_STYLE = ""




class DisplayChannel:
    name: str
    unit: TelemetryName | GwUnit | None = None
    format_string: str
    style: Style
    style_calculator: Optional[Callable[[float | int], Style]] = None
    exists: bool = False
    missing_string: str
    raise_errors: bool = False
    logger: logging.Logger | logging.LoggerAdapter
    reading: Reading | MissingReading
    _missing_reading: MissingReading

    def __init__(
        self,
        name: str,
        channels: ChannelRegistry,
        *,
        format_string: str = DEFAULT_FORMAT_STRING,
        style: Style | str  = DEFAULT_STYLE,
        style_calculator: Optional[Callable[[float|int], Style]] = None,
        missing_string: str = DEFAULT_MISSING_STRING,
        raise_errors: bool = False,
        logger: Optional[logging.Logger | logging.LoggerAdapter] = None
    ) -> None:
        self.name = name
        self._registry = channels

        channel = channels.get(name)
        self.exists = channel is not None

        if isinstance(channel, DataChannel):
            self.unit = channel.TelemetryName
        elif isinstance(channel, DerivedChannel):
            self.unit = channel.OutputUnit

        self.format_string = format_string
        if isinstance(style, str):
            style = Style.parse(style)
        self.style = style
        self.style_calculator = style_calculator
        self.missing_string = missing_string
        self.raise_errors = raise_errors
        if logger is None:
            logger = logging.Logger(__file__)
        self.logger = logger
        self._missing_reading = MissingReading(
            text=Text(
                self.missing_string,
                self.style
            )
        )
        self.reading = self._missing_reading

    def __bool__(self) -> bool:
        return self.exists

    def __str__(self) -> str:
        return str(self.reading.text.markup)

    def __rich_console__(self, _console: Console, _options: ConsoleOptions) -> RenderResult:
        yield self.reading

    @property
    def raw(self) -> Optional[int]:
        if self.exists and self.reading:
            return self.reading.raw
        return None

    @property
    def converted(self) -> Optional[float | int]:
        if self.exists and self.reading:
            return self.reading.converted
        return None

    def get_style(self, converted: float | int) -> Style:
        if self.style_calculator is None or not self.exists:
            return self.style
        return self.style_calculator(converted)

    def convert(self, raw: int) -> float | int:  # noqa
        return float(raw)

    def format(self, converted: float | int) -> Text:
        return Text(
            self.format_string.format(converted=converted),
            style=self.get_style(converted)
        )

    def read_snapshot(self, snap: SnapshotSpaceheat) -> Reading | MissingReading:
        self.reading = self._missing_reading
        if self.exists:
            try:
                for i, reading in enumerate(snap.LatestReadingList):
                    if reading.ChannelName == self.name:
                        raw = snap.LatestReadingList[i].Value
                        converted = self.convert(raw)
                        self.reading = Reading(
                            text=self.format(converted),
                            raw=raw,
                            converted=converted,
                            report_time_unix_ms=snap.LatestReadingList[i].ScadaReadTimeUnixMs,
                            idx=i,
                        )
                        break
            except Exception as e:  # noqa
                self.logger.error(f"ERROR in channel <{self.name}> read")
                self.logger.exception(e)
                if self.raise_errors:
                    raise
        return self.reading

class TemperatureChannel(DisplayChannel):


    def __init__(
        self,
        name: str,
        channels: ChannelRegistry,
        *,
        missing_string: str = "  ---  ",
        style: Style | str = DEFAULT_STYLE,
        style_calculator: Optional[Callable[[float | int], Style]] = fahrenheit_style,
        raise_errors: bool = False,
        logger: Optional[logging.Logger | logging.LoggerAdapter] = None
    ) -> None:

        super().__init__(
            name=name,
            channels=channels,
            format_string=DEFAULT_FORMAT_STRING + "°F",
            style=style,
            style_calculator=style_calculator,
            missing_string=missing_string,
            raise_errors=raise_errors,
            logger=logger,
        )
        if not self.exists:
            return

        if self.unit not in (
                TelemetryName.AirTempCTimes1000,
                TelemetryName.WaterTempCTimes1000,
                TelemetryName.AirTempFTimes1000,
                TelemetryName.WaterTempFTimes1000,
                GwUnit.FahrenheitX100,
            ):
                raise ValueError(
                    f"TemperatureChannel {self.name} has non-temperature "
                    f"unit {self.unit}"
                )


    def convert(self, raw: int) -> float | int:
        if self.unit is None:
            raise ValueError(f"TemperatureChannel {self.name} has no unit metadata!")
        return convert_temp_to_f(
        raw=raw,
        encoding=self.unit,
    )

class TankChannel(TemperatureChannel):

    def __init__(self, *args, **kwargs) -> None:
        kwargs["style_calculator"] = kwargs.get("style_calculator", tank_style)
        super().__init__(*args, **kwargs)

    def __rich_console__(self, _console: Console, _options: ConsoleOptions) -> RenderResult:
        yield self.reading

class PowerChannel(DisplayChannel):
    kW: bool = True

    def __init__(self, *args, **kwargs) -> None:
        self.kW = kwargs.pop('kW', True)
        super().__init__(*args, **kwargs)
        if self.exists and self.unit != TelemetryName.PowerW:
            raise ValueError(
                f"ERROR. Power channel {self.name} expects "
                f"{TelemetryName.PowerW}. Got {self.unit}"
            )

    def convert(self, raw: int) -> float:
        raw2 = float(raw)
        if self.kW:
            raw2 /= 1000
        return round(raw2, 2)

class PumpPowerChannel(PowerChannel):

    def __init__(self, *args, **kwargs) -> None:
        kwargs["kW"] = kwargs.get("kW", False)
        kwargs["missing_string"] = kwargs.get("missing_string", "---")
        super().__init__(*args, **kwargs)

    def format(self, converted: float | int) -> str:
        if converted < PUMP_OFF_THRESHOLD:
            return "OFF"
        return f"{round(converted, 2)}"

class FlowChannel(DisplayChannel):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.exists and self.unit != TelemetryName.GpmTimes100:
            raise ValueError(
                f"ERROR. Flow channel {self.name} expects "
                f"{TelemetryName.GpmTimes100}. Got {self.unit}"
            )
    
    def convert(self, raw: int) -> float:
        raw2 = float(raw)
        raw2 /= 100
        return round(raw2, 1)

class HoneywellThermostatStateChannel(DisplayChannel):

    UNEXPECTED_STYLE = Style(bold=True, color="cyan1")

    STYLES: dict[HoneywellThermostatOperatingState, Style] = {
        HoneywellThermostatOperatingState.idle: Style(color="chartreuse1"),
        HoneywellThermostatOperatingState.heating: Style(color="dark_orange"),
        HoneywellThermostatOperatingState.pending_heat: UNEXPECTED_STYLE,
        HoneywellThermostatOperatingState.pending_cool: UNEXPECTED_STYLE,
        HoneywellThermostatOperatingState.vent_economizer: UNEXPECTED_STYLE,
        HoneywellThermostatOperatingState.cooling: UNEXPECTED_STYLE,
        HoneywellThermostatOperatingState.fan_only: UNEXPECTED_STYLE,
    }

    def __init__(self, *args, **kwargs) -> None:
        kwargs["format_string"] = kwargs.get("format_string", "{converted}")
        super().__init__(*args, **kwargs)

    def convert(self, raw: int) -> float | int:  # noqa
        return raw

    def format(self, converted: float | int) -> Text:
        try:
            state = HoneywellThermostatOperatingState(int(converted))
            return Text(state.name, style=self.STYLES[state])
        except Exception as e:
            self.logger.error(
                f"ERROR converting raw state value <{converted}> to "
                "HoneywellThermostatOperatingState"
            )
            self.logger.exception(e)
            if self.raise_errors:
                raise
        return Text(f"{converted} (?)", style=self.UNEXPECTED_STYLE)

