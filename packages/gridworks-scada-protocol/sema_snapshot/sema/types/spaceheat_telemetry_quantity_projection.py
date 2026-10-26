from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import Quantity
from sema_snapshot.sema.enums import TelemetryName


_PROJECTION = {
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
    TelemetryName.StorageLayer: Quantity.Unitless,
    TelemetryName.BinaryState: Quantity.Unitless,
    TelemetryName.PercentKeep: Quantity.Percent,
}


class SpaceheatTelemetryQuantityProjection(SemaType):
    """Sema: https://schemas.electricity.works/types/spaceheat.telemetry.quantity.projection/001"""

    telemetry_name: TelemetryName
    quantity: Quantity
    type_name: Literal["spaceheat.telemetry.quantity.projection"] = (
        "spaceheat.telemetry.quantity.projection"
    )
    version: Literal["001"] = "001"

    @classmethod
    def project(cls, telemetry_name: TelemetryName) -> Quantity:
        expected = _PROJECTION.get(telemetry_name)
        if expected is None:
            raise ValueError(
                f"No projection defined for telemetry_name {telemetry_name!r}."
            )
        return expected

    @model_validator(mode="after")
    def check_axiom_1(self) -> "SpaceheatTelemetryQuantityProjection":
        """
        Axiom 1: EnumeratedProjectionMapping
        Every (TelemetryName, Quantity) pair SHALL match the mapping declared in
        x-gridworks.projection.table. Any other combination is invalid.
        """
        expected = self.project(self.telemetry_name)
        if expected != self.quantity:
            raise ValueError(
                "Axiom 1 failed: telemetry_name and quantity do not match the enumerated projection."
            )
        return self
