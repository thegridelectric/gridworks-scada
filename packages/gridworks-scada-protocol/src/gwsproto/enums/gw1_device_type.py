from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class Gw1DeviceType(AslEnum):
    """The kind of device a component is built on — a device *category*, not a make/model.

    Scada-side mirror of the `gw1.device.type` registry enum. Used by the scada APPLICATION
    code (generators, actors, drivers) for typo-proof constants and dispatch. The gwsproto
    sema types do NOT use this enum: a component / device-type record carries `DeviceType`
    as an open `pascal.case` string so those types stay version-stable as new device types
    are added. Because `GwStrEnum` is a `str` subclass, `Gw1DeviceType.X` is itself the
    string value — it sets the open field and compares equal to it directly.
    """

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

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.device.type"
