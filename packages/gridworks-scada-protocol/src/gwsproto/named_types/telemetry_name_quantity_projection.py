from typing import Literal
from pydantic import BaseModel, model_validator
from typing_extensions import Self

from gwsproto.enums.telemetry_name import TelemetryName
from gwsproto.enums.gw_quantity import GwQuantity


class TelemetryNameQuantityProjection(BaseModel):
    """Sema: https://schemas.electricity.works/types/spaceheat.telemetry.name.quantity.projection/000"""

    TelemetryName: TelemetryName
    Quantity: GwQuantity
    TypeName: Literal["spaceheat.telemetry.name.quantity.projection"] = (
        "spaceheat.telemetry.name.quantity.projection"
    )
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        valid_pairs = {

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
            TelemetryName.StorageLayer: GwQuantity.Unitless,

            TelemetryName.PercentKeep: GwQuantity.Percent,
        }

        if valid_pairs.get(self.TelemetryName) != self.Quantity:
            raise ValueError(
                f"Invalid TelemetryName → Quantity projection: "
                f"{self.TelemetryName} → {self.Quantity}"
            )

        return self