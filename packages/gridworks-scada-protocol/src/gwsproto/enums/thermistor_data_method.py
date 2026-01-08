from enum import auto

from gw.enums import GwStrEnum


class ThermistorDataMethod(GwStrEnum):
    """
    What method is used to go from raw voltage readings to captured temperature readings.
    Values:
      - SimpleBeta: Using the beta formula with a calibrated open voltage reading, transmitting
        raw polled data.
      - BetaWithExponentialAveraging: Using the beta formula with a calibrated open voltage
        reading, and then some sort of exponential weighted averaging on polled data.

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#thermistordatamethod)
    """

    SimpleBeta = auto()
    BetaWithExponentialAveraging = auto()

    @classmethod
    def default(cls) -> "ThermistorDataMethod":
        return cls.SimpleBeta

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "thermistor.data.method"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
