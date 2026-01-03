from enum import auto

from gw.enums import GwStrEnum


class TelemetryName(GwStrEnum):
    """
    Specifies the name of sensed data reported by a Spaceheat SCADA
    Values:
      - Unknown: Default Value - unknown telemetry name.
      - PowerW: Power in Watts.
      - RelayState: The Telemetry reading belongs to [1 ('Energized'), 0 ('DeEnergized')]
        (relay.energization.state enum).
      - WaterTempCTimes1000: Water temperature, in Degrees Celcius multiplied by 1000.
        Example: 43200 means 43.2 deg Celcius.
      - WaterTempFTimes1000: Water temperature, in Degrees F multiplied by 1000. Example:
        142100 means 142.1 deg Fahrenheit.
      - GpmTimes100: Gallons Per Minute multiplied by 100. Example: 433 means 4.33 gallons
        per minute.
      - CurrentRmsMicroAmps: Current measurement in Root Mean Square MicroAmps.
      - GallonsTimes100: Gallons multipled by 100. This is useful for flow meters that
        report cumulative gallons as their raw output. Example: 55300 means 55.3 gallons.
      - VoltageRmsMilliVolts: Voltage in Root Mean Square MilliVolts.
      - MilliWattHours: Energy in MilliWattHours.
      - MicroHz: Frequency in MicroHz. Example: 59,965,332 means 59.965332 Hz.
      - AirTempCTimes1000: Air temperature, in Degrees Celsius multiplied by 1000. Example:
        6234 means 6.234 deg Celcius.
      - AirTempFTimes1000: Air temperature, in Degrees F multiplied by 1000. Example:
        69329 means 69.329 deg Fahrenheit.
      - ThermostatState: Thermostat State: 0 means idle, 1 means heating, 2 means pending
        heat
      - MicroVolts: Microvolts RMS
      - VoltsTimesTen
      - WattHours
      - StorageLayer

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#spaceheattelemetryname)
      - [More Info](https://gridworks-protocol.readthedocs.io/en/latest/telemetry-name.html)
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
        return "006"
