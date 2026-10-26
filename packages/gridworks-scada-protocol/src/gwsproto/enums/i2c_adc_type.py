from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class I2cAdcType(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/i2c.adc.type/000"""

    Ads1115 = auto()
    Ads1015 = auto()

    @classmethod
    def default(cls) -> "I2cAdcType":
        return cls.Ads1115

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "i2c.adc.type"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
