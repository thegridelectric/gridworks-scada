import logging
from typing import Callable

from typing import Optional

from gwsproto.data_classes.data_channel import DataChannel
from gwsproto.enums import TelemetryName
from gwsproto.named_types import SingleReading
from rich.console import Console
from rich.console import ConsoleOptions
from rich.console import RenderResult
from rich.style import Style
from rich.text import Text

from actors.honeywell_thermostat import HoneywellThermostatOperatingState
from gwsproto.named_types import SnapshotSpaceheat
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
    telemetry_name: TelemetryName = TelemetryName.Unknown
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
        channels: dict[str, DataChannel],
        *,
        format_string: str = DEFAULT_FORMAT_STRING,
        style: Style | str  = DEFAULT_STYLE,
        style_calculator: Optional[Callable[[float|int], Style]] = None,
        missing_string: str = DEFAULT_MISSING_STRING,
        raise_errors: bool = False,
        logger: Optional[logging.Logger | logging.LoggerAdapter] = None
    ) -> None:
        self.name = name
        channel = channels.get(name)
        self.exists = channel is not None
        if self.exists:
            self.telemetry_name = channel.TelemetryName
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
    celsius_data: bool
    fahrenheit_display: bool

    def __init__(
        self,
        name: str,
        channels: dict[str, DataChannel],
        *,
        celcius_data: bool = True,
        fahrenheit_display: bool = True,
        missing_string: str = "  ---  ",
        style: Style | str = DEFAULT_STYLE,
        style_calculator: Optional[Callable[[float | int], Style]] = fahrenheit_style,
        raise_errors: bool = False,
        logger: Optional[logging.Logger | logging.LoggerAdapter] = None
    ) -> None:
        self.fahrenheit_display = fahrenheit_display
        self.celcius_data = celcius_data
        format_string = DEFAULT_FORMAT_STRING + "°"
        if self.fahrenheit_display:
            format_string += "F"
        else:
            format_string += "C"
        super().__init__(
            name=name,
            channels=channels,
            format_string=format_string,
            style=style,
            style_calculator=style_calculator,
            missing_string=missing_string,
            raise_errors=raise_errors,
            logger=logger,
        )
        if self.exists:
            if self.celcius_data:
                valid_telemtery_names = TelemetryName.AirTempCTimes1000, TelemetryName.WaterTempCTimes1000
            else:
                valid_telemtery_names = TelemetryName.AirTempFTimes1000, TelemetryName.WaterTempFTimes1000
            if self.telemetry_name not in valid_telemtery_names:
                raise ValueError(
                    f"ERROR. Temperature channel {self.name} expects data in "
                    f"{valid_telemtery_names} "
                    f"but found {self.telemetry_name} in hardware layout"
                )

    def convert(self, raw: int) -> float | int:
        scaled = raw / 1000
        if self.celcius_data and self.fahrenheit_display:
            return 9 / 5 * scaled + 32
        elif not self.celcius_data and not self.fahrenheit_display:
            return (scaled - 32) * 5 / 9
        return scaled

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
        if self.exists and self.telemetry_name != TelemetryName.PowerW:
            raise ValueError(
                f"ERROR. Power channel {self.name} expects telemetry "
                f"{TelemetryName.PowerW}. Got {self.telemetry_name}"
            )

    def convert(self, raw: int) -> float:
        raw = float(raw)
        if self.kW:
            raw /= 1000
        return round(raw, 2)

class PumpPowerChannel(PowerChannel):

    def __init__(self, *args, **kwargs) -> None:
        kwargs["kW"] = kwargs.get("kW", False)
        kwargs["missing_string"] = kwargs.get("missing_string", "---")
        super().__init__(*args, **kwargs)

    def format(self, converted: float | int) -> str:
        if converted < PUMP_OFF_THRESHOLD:
            return "OFF"
        return f"{round(converted, 2)}"

class UnusedReading(SingleReading):
    Telemetry: TelemetryName

class FlowChannel(DisplayChannel):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.exists and self.telemetry_name != TelemetryName.GpmTimes100:
            raise ValueError(
                f"ERROR. Flow channel {self.name} expects telemetry "
                f"{TelemetryName.GpmTimes100}. Got {self.telemetry_name}"
            )
    
    def convert(self, raw: int) -> float:
        raw = float(raw)
        raw /= 100
        return round(raw, 1)

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

