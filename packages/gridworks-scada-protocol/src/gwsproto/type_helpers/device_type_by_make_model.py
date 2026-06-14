"""Migration bridge: legacy ``spaceheat.make.model`` → new ``gw1.device.type``.

The hardware-layout pass-one rework replaces make/model-as-CAC with a readable
``DeviceType`` (a ``gw1.device.type`` enum value). This dict is the single, obvious
choice of new DeviceType for each legacy ``MakeModel`` the scada actually used — the
mirror of the ``value_descriptions`` "was MakeModel X" notes on the sema enum.

Every value in the new enum has exactly one obvious source MakeModel here, with one
exception: ``AbstractWebServer`` has no make/model origin — it replaces the old
``UNKNOWNMAKE__UNKNOWNMODEL`` web-server hack, so generators set it directly.

This bridge is itself transitional: once layouts/fixtures carry ``DeviceType`` natively,
nothing needs to translate from MakeModel anymore and this file can go.
"""

from gwsproto.enums import MakeModel

DEVICE_TYPE_BY_MAKE_MODEL: dict[MakeModel, str] = {
    MakeModel.EGAUGE__4030: "EgaugePowerMeter",
    MakeModel.GRIDWORKS__TSNAP1: "GridworksTsnap1ScadaBoard",
    MakeModel.GRIDWORKS__SIMPM1: "GridworksSimPowerMeter",
    MakeModel.HUBITAT__C7__LAN1: "HubitatC7Hub",
    MakeModel.AMPHENOL__NTC_10K_THERMISTOR_MA100GG103BN: "Amphenol10kThermistor",
    MakeModel.OMEGA__FTB8010HWPT: "OmegaFtb8010FlowMeter",
    MakeModel.HONEYWELL__T6ZWAVETHERMOSTAT: "HoneywellT6Thermostat",
    MakeModel.TEWA__TT0P10KC3T1051500: "TewaThermistor",
    MakeModel.EKM__HOTSPWM075HD: "EkmFlowMeter",
    MakeModel.KRIDA__DOUBLEEMR16I2CV3: "KridaDoubleRelayBoard16",
    MakeModel.GRIDWORKS__PICOFLOWHALL: "GridworksPicoFlowHall",
    MakeModel.GRIDWORKS__PICOFLOWREED: "GridworksPicoFlowReed",
    MakeModel.SAIER__SENHZG1WA: "SaierFlowSensor",
    MakeModel.DFROBOT__DFR0971_TIMES2: "DfrobotDualAnalogOut",
    MakeModel.GRIDWORKS__TANKMODULE3: "GridworksTankModule3",
    MakeModel.GRIDWORKS__GW101: "GridworksGw101",
    MakeModel.GRIDWORKS__SCADA_GW108: "GridworksScadaGw108",
    MakeModel.GRIDWORKS__SIMMULTITEMP: "GridworksSimSensor",
    MakeModel.GRIDWORKS__SIMBOOL30AMPRELAY: "GridworksSimRelayBank",
}
"""The web server's ``AbstractWebServer`` is intentionally absent — no MakeModel origin."""
