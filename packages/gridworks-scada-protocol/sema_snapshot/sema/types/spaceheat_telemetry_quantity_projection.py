from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import TelemetryName
from sema_snapshot.sema.enums.old_versions.quantity_000 import Quantity000


_PROJECTION = {
    TelemetryName.Unknown: Quantity000.Unknown,
    TelemetryName.PowerW: Quantity000.Power,
    TelemetryName.WattHours: Quantity000.Energy,
    TelemetryName.MilliWattHours: Quantity000.Energy,
    TelemetryName.WaterTempCTimes1000: Quantity000.Temperature,
    TelemetryName.WaterTempFTimes1000: Quantity000.Temperature,
    TelemetryName.AirTempCTimes1000: Quantity000.Temperature,
    TelemetryName.AirTempFTimes1000: Quantity000.Temperature,
    TelemetryName.CelsiusTimes100: Quantity000.Temperature,
    TelemetryName.GpmTimes100: Quantity000.FlowRate,
    TelemetryName.GallonsTimes100: Quantity000.Volume,
    TelemetryName.VoltageRmsMilliVolts: Quantity000.Voltage,
    TelemetryName.VoltsTimesTen: Quantity000.Voltage,
    TelemetryName.VoltsTimes100: Quantity000.Voltage,
    TelemetryName.MicroVolts: Quantity000.Voltage,
    TelemetryName.CurrentRmsMicroAmps: Quantity000.Current,
    TelemetryName.HzTimes100: Quantity000.Frequency,
    TelemetryName.MicroHz: Quantity000.Frequency,
    TelemetryName.RelayState: Quantity000.Unitless,
    TelemetryName.ThermostatState: Quantity000.Unitless,
    TelemetryName.StorageLayer: Quantity000.Unitless,
    TelemetryName.BinaryState: Quantity000.Unitless,
    TelemetryName.PercentKeep: Quantity000.Percent,
}


class SpaceheatTelemetryQuantityProjection(SemaType):
    """Sema: https://schemas.electricity.works/types/spaceheat.telemetry.quantity.projection/000"""

    telemetry_name: TelemetryName
    quantity: Quantity000
    type_name: Literal["spaceheat.telemetry.quantity.projection"] = (
        "spaceheat.telemetry.quantity.projection"
    )
    version: Literal["000"] = "000"

    @classmethod
    def project(cls, telemetry_name: TelemetryName) -> Quantity000:
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
