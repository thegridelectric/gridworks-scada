from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class I2cOperation(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/i2c.operation/001"""

    ReadBit = auto()
    WriteBit = auto()
    ReadReg = auto()
    WriteReg = auto()
    WriteByte = auto()
    ReadBytes = auto()

    @classmethod
    def default(cls) -> "I2cOperation":
        return cls.ReadBit

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "i2c.operation"

    @classmethod
    def enum_version(cls) -> str:
        return "001"
