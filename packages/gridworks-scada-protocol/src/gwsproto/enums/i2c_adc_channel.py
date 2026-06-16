from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class I2cAdcChannel(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/i2c.adc.channel/000"""

    P0 = auto()
    P1 = auto()
    P2 = auto()
    P3 = auto()

    @classmethod
    def default(cls) -> "I2cAdcChannel":
        return cls.P0

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "i2c.adc.channel"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
