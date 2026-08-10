from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class I2cDacChannel(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/i2c.dac.channel/000"""

    A = auto()
    B = auto()
    C = auto()
    D = auto()

    @classmethod
    def default(cls) -> "I2cDacChannel":
        return cls.A

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "i2c.dac.channel"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
