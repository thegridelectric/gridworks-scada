from enum import auto
from gwsproto.enums.gw_str_enum import AslEnum

class HpModel(AslEnum):
    LgHighTempHydroKitPlusMultiV = auto()  
    SamsungFourTonneHydroKit = auto()   
    SamsungFiveTonneHydroKit = auto()
    MitsubishiEcodan = auto()

    @classmethod
    def enum_name(cls) -> str:
        return "hp.model"
