from typing import Any, Literal
from typing_extensions import Self
from pydantic import BaseModel, PositiveInt, model_validator

from gwsproto.property_format import (
    LeftRightDotStr,
    SpaceheatName,
    UUID4Str,
)

from gwsproto.enums import GwUnit, GwQuantity, EmissionMethod
from gwsproto.named_types.unit_quantity_projection import UnitQuantityProjection
from gwsproto.named_types.linear_one_dimensional_calibration import LinearOneDimensionalCalibration

class DerivedChannelGt(BaseModel):
    """Sema: https://schemas.electricity.works/types/derived.channel.gt/002"""

    Id: UUID4Str
    Name: SpaceheatName
    CreatedByNodeName: SpaceheatName
    Strategy: SpaceheatName
    InputChannelNames: list[SpaceheatName]
    OutputUnit: GwUnit
    OutputQuantity: GwQuantity
    EmissionMethod: EmissionMethod
    AsyncEmitDelta: PositiveInt | None = None
    EmitPeriodS: PositiveInt | None = None
    Parameters: dict[str, Any] | None = None
    DisplayName: str
    TerminalAssetAlias: LeftRightDotStr
    TypeName: Literal["derived.channel.gt"] = "derived.channel.gt"
    Version: Literal["002"] = "002"


    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Emission semantics consistency.

        - OnTrigger => no EmitPeriodS, no AsyncEmitDelta
        - Periodic => EmitPeriodS exists, no AsyncEmitDelta
        - AsyncAndPeriodic => EmitPeriodS exists, AsyncEmitDelta exists
        """
        method = self.EmissionMethod

        match method:
            case EmissionMethod.OnTrigger:
                if self.EmitPeriodS is not None:
                    raise ValueError(
                        "EmissionMethod.OnTrigger must not define EmitPeriodS"
                    )
                if self.AsyncEmitDelta is not None:
                    raise ValueError(
                        "EmissionMethod.OnTrigger must not define AsyncEmitDelta"
                    )

            case EmissionMethod.Periodic:
                if self.EmitPeriodS is None:
                    raise ValueError(
                        "EmissionMethod.Periodic requires EmitPeriodS"
                    )
                if self.AsyncEmitDelta is not None:
                    raise ValueError(
                        "EmissionMethod.Periodic must not define AsyncEmitDelta"
                    )

            case EmissionMethod.AsyncAndPeriodic:
                if self.EmitPeriodS is None:
                    raise ValueError(
                        "EmissionMethod.AsyncAndPeriodic requires EmitPeriodS"
                    )
                if self.AsyncEmitDelta is None:
                    raise ValueError(
                        "EmissionMethod.AsyncAndPeriodic requires AsyncEmitDelta"
                    )

            case _:
                raise ValueError(
                    f"Unknown EmissionMethod {method}"
                )

        return self

    
    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: OutputUnitQuantityConsistency

        OutputQuantity SHALL equal the Quantity defined by the canonical
        gw1.unit.quantity.projection/000 instance for the specified OutputUnit.
        """
        try:
            UnitQuantityProjection(
                Unit=self.OutputUnit,
                Quantity=self.OutputQuantity,
            )
        except Exception as e:
            raise ValueError(
                f"OutputUnit {self.OutputUnit} and "
                f"OutputQuantity {self.OutputQuantity} "
                f"do not form a valid gw1.unit.quantity.projection"
            ) from e

        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: AffineStrategyRequiresCalibration
        If Strategy == "affine", then Parameters must contain a valid
        linear.one.dimensional.calibration instance under the key "Calibration".
        """

        if self.Strategy != "affine":
            return self

        if self.Parameters is None:
            raise ValueError(
                "Strategy 'affine' requires Parameters to be present"
            )

        calibration_data = self.Parameters.get("Calibration")
        if calibration_data is None:
            raise ValueError(
                "Strategy 'affine' requires Parameters['Calibration']"
            )

        try:
            LinearOneDimensionalCalibration(**calibration_data)
        except Exception as e:
            raise ValueError(
                "Axiom 3 violated! Parameters['Calibration'] must be a valid "
                "linear.one.dimensional.calibration instance"
            ) from e

        return self