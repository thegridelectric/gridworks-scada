"""
Maps legacy TelemetryName and modern GwUnit encodings
to semantic GwQuantity.

This module defines the authoritative mapping used to interpret
channel encodings during the transition from TelemetryName to GwUnit.

Rules:
- Every GwUnit and TelemetryName must appear as a key.
- Unknown encodings map to GwQuantity.Unknown.
- State-like or categorical encodings map to GwQuantity.Unitless.
- This mapping is semantic, not about scaling or precision.
"""


from gwsproto.enums.gw_quantity import GwQuantity
from gwsproto.enums.gw_unit import GwUnit
from gwsproto.enums.telemetry_name import TelemetryName


UNIT_TO_QUANTITY: dict[GwUnit | TelemetryName, GwQuantity] = {

    GwUnit.Unknown: GwQuantity.Unknown,
    GwUnit.Unitless: GwQuantity.Unitless,
    GwUnit.FahrenheitX100: GwQuantity.Temperature,
    GwUnit.Watts: GwQuantity.Power,
    GwUnit.WattHours: GwQuantity.Energy,
    GwUnit.Gallons: GwQuantity.Volume,
    GwUnit.GpmX100: GwQuantity.FlowRate,
    
    TelemetryName.Unknown: GwQuantity.Unknown,

    TelemetryName.PowerW: GwQuantity.Power,
    TelemetryName.WattHours: GwQuantity.Energy,
    TelemetryName.MilliWattHours: GwQuantity.Energy,

    TelemetryName.WaterTempCTimes1000: GwQuantity.Temperature,
    TelemetryName.WaterTempFTimes1000: GwQuantity.Temperature,
    TelemetryName.AirTempCTimes1000: GwQuantity.Temperature,
    TelemetryName.AirTempFTimes1000: GwQuantity.Temperature,
    TelemetryName.CelsiusTimes100: GwQuantity.Temperature,

    TelemetryName.GpmTimes100: GwQuantity.FlowRate,
    TelemetryName.GallonsTimes100: GwQuantity.Volume,

    TelemetryName.VoltageRmsMilliVolts: GwQuantity.Voltage,
    TelemetryName.VoltsTimesTen: GwQuantity.Voltage,
    TelemetryName.VoltsTimes100: GwQuantity.Voltage,
    TelemetryName.MicroVolts: GwQuantity.Voltage,

    TelemetryName.CurrentRmsMicroAmps: GwQuantity.Current,

    TelemetryName.HzTimes100: GwQuantity.Frequency,
    TelemetryName.MicroHz: GwQuantity.Frequency,

    TelemetryName.RelayState: GwQuantity.Unitless,
    TelemetryName.ThermostatState: GwQuantity.Unitless,

    TelemetryName.PercentKeep: GwQuantity.Percent,
    TelemetryName.StorageLayer: GwQuantity.Unitless,
    
}
