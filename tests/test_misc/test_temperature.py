"""The Temperature record: a raw channel value with its declared encoding."""

import pytest

from gwsproto.conversions.temperature import Temperature
from gwsproto.enums import TelemetryName, Unit


@pytest.mark.parametrize(
    ("raw", "encoding", "f"),
    [
        (2000, TelemetryName.CelsiusTimes100, 68.0),
        (20_000, TelemetryName.WaterTempCTimes1000, 68.0),
        (20_000, TelemetryName.AirTempCTimes1000, 68.0),
        (68_000, TelemetryName.AirTempFTimes1000, 68.0),
        (68_000, TelemetryName.WaterTempFTimes1000, 68.0),
        (6800, Unit.FahrenheitX100, 68.0),
    ],
)
def test_every_temperature_encoding_answers_in_f(raw: int, encoding: TelemetryName | Unit, f: float) -> None:
    assert Temperature(raw, encoding).f == pytest.approx(f)


def test_a_whole_degree_f_setpoint_survives_celsius_times_100_within_a_hundredth() -> None:
    raw_c = round((69 - 32) * 5 / 9 * 100)
    assert Temperature(raw_c, TelemetryName.CelsiusTimes100).f == pytest.approx(69.0, abs=0.01)


@pytest.mark.parametrize(
    ("encoding", "raw"),
    [
        (TelemetryName.CelsiusTimes100, 2000),
        (TelemetryName.WaterTempCTimes1000, 20_000),
        (TelemetryName.AirTempCTimes1000, 20_000),
        (TelemetryName.AirTempFTimes1000, 68_000),
        (TelemetryName.WaterTempFTimes1000, 68_000),
        (Unit.FahrenheitX100, 6800),
    ],
)
def test_a_measurement_encodes_into_every_temperature_encoding(encoding: TelemetryName | Unit, raw: int) -> None:
    assert Temperature.from_c(20.0, encoding) == Temperature(raw, encoding)
    assert Temperature.from_f(68.0, encoding) == Temperature(raw, encoding)


def test_a_whole_degree_f_measurement_rounds_into_celsius_times_100() -> None:
    assert Temperature.from_f(69, TelemetryName.CelsiusTimes100).raw == 2056


@pytest.mark.parametrize("encoding", [TelemetryName.PowerW, Unit.Watts])
def test_a_measurement_is_refused_a_non_temperature_encoding(encoding: TelemetryName | Unit) -> None:
    with pytest.raises(ValueError):
        Temperature.from_c(20.0, encoding)


@pytest.mark.parametrize("encoding", [TelemetryName.PowerW, Unit.Watts])
def test_a_non_temperature_encoding_is_refused_at_construction(encoding: TelemetryName | Unit) -> None:
    with pytest.raises(ValueError):
        Temperature(100, encoding)


def test_temperatures_order_across_encodings() -> None:
    c = Temperature(2000, TelemetryName.CelsiusTimes100)  # 68 F
    f = Temperature(6900, Unit.FahrenheitX100)
    assert c < f
    assert min(f, c) is c
