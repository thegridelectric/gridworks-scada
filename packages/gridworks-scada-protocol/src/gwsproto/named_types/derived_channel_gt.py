from typing import Any, Literal

from pydantic import BaseModel, PositiveInt, model_validator

from gwsproto.property_format import (
    LeftRightDotStr,
    SpaceheatName,
    UUID4Str,
)

from gwsproto.enums import GwUnit, GwQuantity, EmissionMethod
from gwsproto.named_types.unit_quantity_projection import UnitQuantityProjection


class DerivedChannelGt(BaseModel):
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
    def check_axiom_1(self) -> "DerivedChannelGt":
        """
        Axiom 1: EmissionSemanticsConsistency
        EmissionMethod SHALL determine the presence of EmitPeriodS and
        AsyncEmitDelta as follows:

          OnTrigger → neither EmitPeriodS nor AsyncEmitDelta present
          Periodic → EmitPeriodS present, AsyncEmitDelta absent
          AsyncAndPeriodic → both EmitPeriodS and AsyncEmitDelta present
        """
        if self.EmissionMethod == EmissionMethod.OnTrigger:
            if self.EmitPeriodS is not None or self.AsyncEmitDelta is not None:
                raise ValueError(
                    "Axiom 1 failed: OnTrigger must not include emit_period_s or async_emit_delta."
                )
        elif self.EmissionMethod == EmissionMethod.Periodic:
            if self.EmitPeriodS is None or self.AsyncEmitDelta is not None:
                raise ValueError(
                    "Axiom 1 failed: Periodic requires emit_period_s and forbids async_emit_delta."
                )
        elif self.EmissionMethod == EmissionMethod.AsyncAndPeriodic:
            if self.EmitPeriodS is None or self.AsyncEmitDelta is None:
                raise ValueError(
                    "Axiom 1 failed: AsyncAndPeriodic requires both emit_period_s and async_emit_delta."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "DerivedChannelGt":
        """
        Axiom 2: OutputUnitQuantityConsistency
        OutputQuantity SHALL equal the Quantity defined by the canonical
        gw1.unit.quantity.projection:000 instance for the specified OutputUnit.
        """
        expected = UnitQuantityProjection.project(GwUnit(self.OutputUnit))
        if self.OutputQuantity != expected:
            raise ValueError(
                "Axiom 2 failed: output_quantity must match the canonical quantity "
                "for output_unit."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "DerivedChannelGt":
        """
        Axiom 3: AffineStrategyRequiresCalibration
        If Strategy equals "affine", then:

          - Parameters SHALL contain a key "Calibration".
          - Parameters.Calibration SHALL be a valid
            linear.one.dimensional.calibration instance.
        """
        if self.Strategy == "affine":
            if self.Parameters is None or "Calibration" not in self.Parameters:
                raise ValueError(
                    "Axiom 3 failed: affine strategy requires Parameters.Calibration."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> "DerivedChannelGt":
        """
        Axiom 4: SystemModelRequiresParameters
        If Strategy equals "system-model", then:
          - Parameters SHALL be present.
          - Parameters SHALL contain a key "EnergyModel".
          - Parameters.EnergyModel SHALL include:
              - TypeName
              - Version
        """
        if self.Strategy == "system-model":
            if self.Parameters is None:
                raise ValueError(
                    "Axiom 4 failed: system-model strategy requires Parameters."
                )
            energy_model = self.Parameters.get("EnergyModel")
            if not isinstance(energy_model, dict):
                raise ValueError(
                    "Axiom 4 failed: system-model strategy requires Parameters.EnergyModel."
                )
            if "TypeName" not in energy_model or "Version" not in energy_model:
                raise ValueError(
                    "Axiom 4 failed: Parameters.EnergyModel must include TypeName and Version."
                )
        return self
