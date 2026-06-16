from typing import Any, Literal
from typing_extensions import Self
from pydantic import BaseModel, PositiveInt, model_validator

from gwsproto.property_format import (
    LeftRightDotStr,
    SpaceheatName,
    UUID4Str,
)

from gwsproto.enums import GwUnit, GwQuantity, EmissionMethod
from gwsproto.enums.unit_quantity import UNIT_TO_QUANTITY


class DerivedChannelGt(BaseModel):
    Id: UUID4Str
    Name: SpaceheatName
    CreatedByNodeName: SpaceheatName
    Strategy: SpaceheatName
    InputChannelNames: list[SpaceheatName] = []
    OutputUnit: GwUnit | None = None
    # OutputQuantity mirrors the gwta derived.channel.gt/002 field. It is the canonical
    # quantity for OutputUnit (see gwsproto.enums.unit_quantity.UNIT_TO_QUANTITY). Kept
    # Optional because gwsproto carries trigger-only derived channels with no OutputUnit.
    OutputQuantity: GwQuantity | None = None
    EmissionMethod: EmissionMethod
    AsyncEmitDelta: PositiveInt | None = None
    EmitPeriodS: PositiveInt | None = None
    Parameters: dict[str, Any] | None = None
    DisplayName: str
    TerminalAssetAlias: LeftRightDotStr
    TypeName: Literal["derived.channel.gt"] = "derived.channel.gt"
    Version: Literal["002"] = "002"

    @model_validator(mode="after")
    def derive_output_quantity(self) -> Self:
        """Mirror gwta's OutputUnitQuantityConsistency axiom: OutputQuantity is the
        canonical quantity for OutputUnit. Auto-fill when OutputUnit is set and the
        quantity was not supplied (so builders need only set the unit)."""
        if self.OutputUnit is not None and self.OutputQuantity is None:
            self.OutputQuantity = UNIT_TO_QUANTITY.get(self.OutputUnit)
        return self

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
