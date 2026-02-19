from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class PrimaryPumpControl(AslEnum):
    """

    Values:
      - HeatPump
      - Scada

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#primarypumpcontrol)
    """

    HeatPump = auto()
    Scada = auto()

    @classmethod
    def default(cls) -> "PrimaryPumpControl":
        return cls.HeatPump

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "primary.pump.control"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
