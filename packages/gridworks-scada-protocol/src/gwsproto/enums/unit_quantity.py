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


from gwsproto.enums.quantity import Quantity
from gwsproto.enums.unit import Unit
from gwsproto.enums.telemetry_name import TelemetryName


UNIT_TO_QUANTITY: dict[Unit | TelemetryName, Quantity] = {

    Unit.Unknown: Quantity.Unknown,
    Unit.Unitless: Quantity.Unitless,
    Unit.FahrenheitX100: Quantity.Temperature,
    Unit.Watts: Quantity.Power,
    Unit.WattHours: Quantity.Energy,
    Unit.Gallons: Quantity.Volume,
    Unit.GpmX100: Quantity.FlowRate,
    Unit.Seconds: Quantity.Time,
    Unit.SecondsX10: Quantity.Time,
    Unit.Milliseconds: Quantity.Time,

    TelemetryName.Unknown: Quantity.Unknown,

    TelemetryName.PowerW: Quantity.Power,
    TelemetryName.WattHours: Quantity.Energy,
    TelemetryName.MilliWattHours: Quantity.Energy,

    TelemetryName.WaterTempCTimes1000: Quantity.Temperature,
    TelemetryName.WaterTempFTimes1000: Quantity.Temperature,
    TelemetryName.AirTempCTimes1000: Quantity.Temperature,
    TelemetryName.AirTempFTimes1000: Quantity.Temperature,
    TelemetryName.CelsiusTimes100: Quantity.Temperature,

    TelemetryName.GpmTimes100: Quantity.FlowRate,
    TelemetryName.GallonsTimes100: Quantity.Volume,

    TelemetryName.VoltageRmsMilliVolts: Quantity.Voltage,
    TelemetryName.VoltsTimesTen: Quantity.Voltage,
    TelemetryName.VoltsTimes100: Quantity.Voltage,
    TelemetryName.MicroVolts: Quantity.Voltage,

    TelemetryName.CurrentRmsMicroAmps: Quantity.Current,

    TelemetryName.HzTimes100: Quantity.Frequency,
    TelemetryName.MicroHz: Quantity.Frequency,

    TelemetryName.RelayState: Quantity.Unitless,
    TelemetryName.ThermostatState: Quantity.Unitless,
    TelemetryName.BinaryState: Quantity.Unitless,

    TelemetryName.PercentKeep: Quantity.Percent,
    TelemetryName.StorageLayer: Quantity.Unitless,
    
}
