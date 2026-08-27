from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class MakeModel(AslEnum):

    UNKNOWNMAKE__UNKNOWNMODEL = auto()
    EGAUGE__4030 = auto()
    NCD__PR814SPST = auto()
    ADAFRUIT__642 = auto()
    GRIDWORKS__TSNAP1 = auto()
    GRIDWORKS__WATERTEMPHIGHPRECISION = auto()
    GRIDWORKS__SIMPM1 = auto()
    SCHNEIDERELECTRIC__IEM3455 = auto()
    GRIDWORKS__SIMBOOL30AMPRELAY = auto()
    OPENENERGY__EMONPI = auto()
    GRIDWORKS__SIMTSNAP1 = auto()
    ATLAS__EZFLO = auto()
    HUBITAT__C7__LAN1 = auto()
    GRIDWORKS__TANK_MODULE_1 = auto()
    FIBARO__ANALOG_TEMP_SENSOR = auto()
    AMPHENOL__NTC_10K_THERMISTOR_MA100GG103BN = auto()
    YHDC__SCT013100 = auto()
    MAGNELAB__SCT0300050 = auto()
    GRIDWORKS__MULTITEMP1 = auto()
    KRIDA__EMR16I2CV3 = auto()
    OMEGA__FTB8007HWPT = auto()
    ISTEC_4440 = auto()
    OMEGA__FTB8010HWPT = auto()
    BELIMO__BALLVALVE232VS = auto()
    BELIMO__DIVERTERB332L = auto()
    TACO__0034EPLUS = auto()
    TACO__007E = auto()
    ARMSTRONG__COMPASSH = auto()
    HONEYWELL__T6ZWAVETHERMOSTAT = auto()
    PRMFILTRATION__WM075 = auto()
    BELLGOSSETT__ECOCIRC20_18 = auto()
    TEWA__TT0P10KC3T1051500 = auto()
    EKM__HOTSPWM075HD = auto()
    GRIDWORKS__SIMMULTITEMP = auto()
    GRIDWORKS__SIMTOTALIZER = auto()
    KRIDA__DOUBLEEMR16I2CV3 = auto()
    GRIDWORKS__SIMDOUBLE16PINI2CRELAY = auto()
    GRIDWORKS__TANKMODULE2 = auto()
    GRIDWORKS__PICOFLOWHALL = auto()
    GRIDWORKS__PICOFLOWREED = auto()
    SAIER__SENHZG1WA = auto()
    DFROBOT__DFR0971_TIMES2 = auto()
    GRIDWORKS__TANKMODULE3 = auto()
    GRIDWORKS__GW101 = auto()
    GRIDWORKS__SCADA_GW108 = auto()

    @classmethod
    def default(cls) -> "MakeModel":
        return cls.UNKNOWNMAKE__UNKNOWNMODEL

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "spaceheat.make.model"

    @classmethod
    def enum_version(cls) -> str:
        return "007"
