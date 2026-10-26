from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class I2cExpanderType(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/i2c.expander.type/000"""

    Tca9555 = auto()
    Pcf8575 = auto()

    @classmethod
    def default(cls) -> "I2cExpanderType":
        return cls.Tca9555

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "i2c.expander.type"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
