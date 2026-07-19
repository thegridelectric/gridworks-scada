from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class DeviceType(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/gw1.device.type/001"""

    EgaugePowerMeter = auto()
    GridworksTsnap1ScadaBoard = auto()
    GridworksSimPowerMeter = auto()
    HubitatC7Hub = auto()
    Amphenol10kThermistor = auto()
    OmegaFtb8010FlowMeter = auto()
    HoneywellT6Thermostat = auto()
    TewaThermistor = auto()
    EkmFlowMeter = auto()
    KridaDoubleRelayBoard16 = auto()
    GridworksPicoFlowHall = auto()
    GridworksPicoFlowReed = auto()
    SaierFlowSensor = auto()
    DfrobotDualAnalogOut = auto()
    GridworksTankModule3 = auto()
    GridworksGw101 = auto()
    GridworksScadaGw108 = auto()
    GridworksSimSensor = auto()
    GridworksSimRelayBank = auto()
    AbstractWebServer = auto()
    Gw108I2cRelay = auto()
    Gw108GpioRelay = auto()
    SamsungAE055FCYDCG = auto()
    SamsungAE055FEYMCG = auto()
    Gw108Adc = auto()


    @classmethod
    def default(cls) -> "DeviceType":
        return cls.EgaugePowerMeter

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.device.type"

    @classmethod
    def enum_version(cls) -> str:
        return "001"