from gwsproto.enums import TelemetryName
from gwsproto.enums import GwUnit


def convert_temp_to_f(raw: int, encoding: TelemetryName | GwUnit) -> float:
    if encoding == GwUnit.FahrenheitX100:
        return raw / 100

    if encoding in (
        TelemetryName.WaterTempCTimes1000,
        TelemetryName.AirTempCTimes1000,
    ):
        return raw / 1000 * 9 / 5 + 32

    if encoding in (
        TelemetryName.WaterTempFTimes1000,
        TelemetryName.AirTempFTimes1000,
    ):
        return raw / 1000

    raise ValueError(f"Unknown temperature encoding: {encoding}")