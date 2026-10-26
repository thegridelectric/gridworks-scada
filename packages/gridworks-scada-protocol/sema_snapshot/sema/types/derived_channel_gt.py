from typing import Any, Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import EmissionMethod
from sema_snapshot.sema.enums import Quantity
from sema_snapshot.sema.enums import Unit
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.unit_quantity_projection import UnitQuantityProjection


class DerivedChannelGt(SemaType):
    """Sema: https://schemas.electricity.works/types/derived.channel.gt/003"""

    id: UUID4Str
    name: SpaceheatName
    created_by_node_name: SpaceheatName
    strategy: SpaceheatName
    input_channel_names: list[SpaceheatName]
    output_unit: Unit
    output_quantity: Quantity
    emission_method: EmissionMethod
    async_emit_delta: PositiveInt | None = None
    emit_period_s: PositiveInt | None = None
    parameters: dict[str, Any] | None = None
    display_name: str
    terminal_asset_alias: LeftRightDot
    type_name: Literal["derived.channel.gt"] = "derived.channel.gt"
    version: Literal["003"] = "003"

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
        if self.emission_method == EmissionMethod.OnTrigger:
            if self.emit_period_s is not None or self.async_emit_delta is not None:
                raise ValueError(
                    "Axiom 1 failed: OnTrigger must not include emit_period_s or async_emit_delta."
                )
        elif self.emission_method == EmissionMethod.Periodic:
            if self.emit_period_s is None or self.async_emit_delta is not None:
                raise ValueError(
                    "Axiom 1 failed: Periodic requires emit_period_s and forbids async_emit_delta."
                )
        elif self.emission_method == EmissionMethod.AsyncAndPeriodic:
            if self.emit_period_s is None or self.async_emit_delta is None:
                raise ValueError(
                    "Axiom 1 failed: AsyncAndPeriodic requires both emit_period_s and async_emit_delta."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "DerivedChannelGt":
        """
        Axiom 2: OutputUnitQuantityConsistency
        OutputQuantity SHALL equal the Quantity defined by the canonical
        gw1.unit.quantity.projection:001 instance for the specified OutputUnit.
        """
        expected = UnitQuantityProjection.project(Unit(self.output_unit.value))
        if self.output_quantity != expected:
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
        if self.strategy == "affine":
            if self.parameters is None or "Calibration" not in self.parameters:
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
        if self.strategy == "system-model":
            if self.parameters is None:
                raise ValueError(
                    "Axiom 4 failed: system-model strategy requires Parameters."
                )
            energy_model = self.parameters.get("EnergyModel")
            if not isinstance(energy_model, dict):
                raise ValueError(
                    "Axiom 4 failed: system-model strategy requires Parameters.EnergyModel."
                )
            if "TypeName" not in energy_model or "Version" not in energy_model:
                raise ValueError(
                    "Axiom 4 failed: Parameters.EnergyModel must include TypeName and Version."
                )
        return self
