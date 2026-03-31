from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator
from typing_extensions import Self

from gwsproto.enums import GwQuantity, TelemetryName as TelemetryNameEnum
from gwsproto.enums.unit_quantity import UNIT_TO_QUANTITY


class SpaceheatTelemetryQuantityProjection(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/spaceheat.telemetry.quantity.projection/000
    """

    TelemetryName: TelemetryNameEnum
    Quantity: GwQuantity
    TypeName: Literal[
        "spaceheat.telemetry.quantity.projection"
    ] = "spaceheat.telemetry.quantity.projection"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(use_enum_values=True)

    @classmethod
    def canonical(
        cls, telemetry_name: TelemetryNameEnum
    ) -> "SpaceheatTelemetryQuantityProjection":
        return cls(
            TelemetryName=telemetry_name,
            Quantity=UNIT_TO_QUANTITY[telemetry_name],
        )

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: EnumeratedProjectionMapping.
        Quantity must match the canonical projection for TelemetryName.
        """
        expected_quantity = UNIT_TO_QUANTITY[self.TelemetryName]
        if self.Quantity != expected_quantity:
            raise ValueError(
                "Axiom 1 violated! "
                f"TelemetryName {self.TelemetryName} maps to Quantity "
                f"{expected_quantity}, not {self.Quantity}"
            )
        return self
