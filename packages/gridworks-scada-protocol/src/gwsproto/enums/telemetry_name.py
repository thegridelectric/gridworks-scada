from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class TelemetryName(AslEnum):
    """
    Sema: https://schemas.electricity.works/enums/spaceheat.telemetry.name/007
    """

    Unknown = auto()
    PowerW = auto()
    RelayState = auto()
    WaterTempCTimes1000 = auto()
    WaterTempFTimes1000 = auto()
    GpmTimes100 = auto()
    CurrentRmsMicroAmps = auto()
    GallonsTimes100 = auto()
    VoltageRmsMilliVolts = auto()
    MilliWattHours = auto()
    MicroHz = auto()
    AirTempCTimes1000 = auto()
    AirTempFTimes1000 = auto()
    ThermostatState = auto()
    MicroVolts = auto()
    VoltsTimesTen = auto()
    WattHours = auto()
    StorageLayer = auto()
    PercentKeep = auto()
    CelsiusTimes100 = auto()
    VoltsTimes100 = auto()
    HzTimes100 = auto()
    BinaryState = auto()

    @classmethod
    def default(cls) -> "TelemetryName":
        return cls.Unknown

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "spaceheat.telemetry.name"

    @classmethod
    def enum_version(cls) -> str:
        return "007"
