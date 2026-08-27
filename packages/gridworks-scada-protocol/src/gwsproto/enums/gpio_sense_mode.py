from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class GpioSenseMode(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gpio.sense.mode/000"""

    Polling = auto()
    EdgeDetect = auto()

    @classmethod
    def default(cls) -> "GpioSenseMode":
        return cls.Polling

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gpio.sense.mode"

    @classmethod 
    def enum_version(cls) -> str:
        return "000"