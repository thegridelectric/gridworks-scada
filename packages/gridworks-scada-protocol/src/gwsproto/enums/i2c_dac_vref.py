from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class I2cDacVref(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/i2c.dac.vref/000"""

    Internal = auto()
    Vdd = auto()

    @classmethod
    def default(cls) -> "I2cDacVref":
        return cls.Internal

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "i2c.dac.vref"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
