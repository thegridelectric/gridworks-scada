from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class HpBossState(AslEnum):
    PreparingToTurnOn = auto()
    HpOn = auto()
    HpOff = auto()

    @classmethod
    def default(cls) -> "HpBossState":
        return cls.HpOff

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.hp.boss.state"

    @classmethod
    def version(cls) -> str:
        return "000"