from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class I2cDacType(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/i2c.dac.type/000"""

    Mcp4728 = auto()
    Mcp4725 = auto()

    @classmethod
    def default(cls) -> "I2cDacType":
        return cls.Mcp4728

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "i2c.dac.type"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
