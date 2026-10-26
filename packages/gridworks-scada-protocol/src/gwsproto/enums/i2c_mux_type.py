from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class I2cMuxType(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/i2c.mux.type/000"""

    Tca9548a = auto()

    @classmethod
    def default(cls) -> "I2cMuxType":
        return cls.Tca9548a

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "i2c.mux.type"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
