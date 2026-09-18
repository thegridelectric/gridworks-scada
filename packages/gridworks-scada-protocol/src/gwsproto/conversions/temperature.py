from dataclasses import dataclass

from gwsproto.enums import TelemetryName
from gwsproto.enums import Unit


def convert_temp_to_f(raw: int, encoding: TelemetryName | Unit) -> float:
    if encoding == Unit.FahrenheitX100:
        return raw / 100

    if encoding in (
        TelemetryName.WaterTempCTimes1000,
        TelemetryName.AirTempCTimes1000,
    ):
        return raw / 1000 * 9 / 5 + 32

    if encoding == TelemetryName.CelsiusTimes100:
        return raw / 100 * 9 / 5 + 32

    if encoding in (
        TelemetryName.WaterTempFTimes1000,
        TelemetryName.AirTempFTimes1000,
    ):
        return raw / 1000

    raise ValueError(f"Unknown temperature encoding: {encoding}")


def encode_temp_c(c: float, encoding: TelemetryName | Unit) -> int:
    if encoding == Unit.FahrenheitX100:
        return round((c * 9 / 5 + 32) * 100)

    if encoding in (
        TelemetryName.WaterTempCTimes1000,
        TelemetryName.AirTempCTimes1000,
    ):
        return round(c * 1000)

    if encoding == TelemetryName.CelsiusTimes100:
        return round(c * 100)

    if encoding in (
        TelemetryName.WaterTempFTimes1000,
        TelemetryName.AirTempFTimes1000,
    ):
        return round((c * 9 / 5 + 32) * 1000)

    raise ValueError(f"Unknown temperature encoding: {encoding}")


@dataclass(frozen=True)
class Temperature:
    """A channel's raw temperature value with the encoding the channel
    declares. Construction raises ValueError on an encoding that is not a
    temperature. Orders by temperature across encodings; equality is the
    same raw value in the same encoding."""

    raw: int
    encoding: TelemetryName | Unit

    def __post_init__(self) -> None:
        convert_temp_to_f(self.raw, self.encoding)

    @classmethod
    def from_c(cls, c: float, encoding: TelemetryName | Unit) -> "Temperature":
        """A measurement in degrees Celsius, rounded into `encoding`."""
        return cls(encode_temp_c(c, encoding), encoding)

    @classmethod
    def from_f(cls, f: float, encoding: TelemetryName | Unit) -> "Temperature":
        """A measurement in degrees Fahrenheit, rounded into `encoding`."""
        return cls(encode_temp_c((f - 32) * 5 / 9, encoding), encoding)

    @property
    def f(self) -> float:
        """Degrees Fahrenheit."""
        return convert_temp_to_f(self.raw, self.encoding)

    def __lt__(self, other: "Temperature") -> bool:
        return self.f < other.f

    def __le__(self, other: "Temperature") -> bool:
        return self.f <= other.f

    def __gt__(self, other: "Temperature") -> bool:
        return self.f > other.f

    def __ge__(self, other: "Temperature") -> bool:
        return self.f >= other.f
