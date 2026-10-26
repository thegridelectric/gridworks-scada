from typing import Annotated, List, Literal, Optional, Union

from pydantic import ConfigDict, Field, model_validator
from typing_extensions import Self

from gwsproto.enums import PrimaryFlowSource, PrimaryPumpOwner, RefrigerantCycle
from gwsproto.named_types.boiler_backup import BoilerBackup
from gwsproto.named_types.element_backup import ElementBackup
from gwsproto.named_types.hvac_zone import HvacZone
from gwsproto.named_types import water_store
from gwsproto.named_types.zone_call_circuit import ZoneCallCircuit
from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class Hydronic(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/gw.hydronic/000
    """

    Zones: List[HvacZone]
    ZoneCallCircuits: List[ZoneCallCircuit]
    # The class attribute shadows the type name inside the class body, so the
    # annotation goes through the module.
    WaterStore: Optional[water_store.WaterStore] = None
    Backup: Optional[
        Annotated[Union[BoilerBackup, ElementBackup], Field(discriminator="TypeName")]
    ] = None
    PrimaryFlowSource: PrimaryFlowSource
    PrimaryPumpOwner: PrimaryPumpOwner
    RefrigerantCycle: RefrigerantCycle
    HpCommandNodeName: Optional[SpaceheatName] = None
    TypeName: Literal["gw.hydronic"] = "gw.hydronic"
    Version: Literal["000"] = "000"
    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Cardinality
        The number of Zones SHALL be between 1 and 6 inclusive.
        """
        if not 1 <= len(self.Zones) <= 6:
            raise ValueError(
                "Axiom 1 (Cardinality) failed: number of Zones "
                f"({len(self.Zones)}) must be between 1 and 6 inclusive."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: CircuitResolution
        a. Every circuit's ServesZone SHALL equal the Name of a zone in
        Zones. b. The circuit at 1-based place i in ZoneCallCircuits SHALL
        have CircuitPosition i.
        c. No two zones SHALL share a Name.
        """
        circuits = self.ZoneCallCircuits
        zone_names = {z.Name for z in self.Zones}
        for c in circuits:
            if c.ServesZone not in zone_names:
                raise ValueError(
                    "Axiom 2 (CircuitResolution) failed: ServesZone "
                    f"{c.ServesZone!r} does not name a zone in Zones."
                )
        positions = [c.CircuitPosition for c in circuits]
        if positions != list(range(1, len(circuits) + 1)):
            raise ValueError(
                "Axiom 2 (CircuitResolution) failed: CircuitPosition values "
                f"{positions} are not each circuit's 1-based place in ZoneCallCircuits."
            )
        names = [z.Name for z in self.Zones]
        if len(names) != len(set(names)):
            raise ValueError(
                f"Axiom 2 (CircuitResolution) failed: zone Names {names} are not distinct."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: PrimaryCircuit
        a. Every zone's PrimaryCircuitPosition SHALL equal the
        CircuitPosition of a circuit whose ServesZone equals the zone's
        Name. b. That circuit SHALL carry SetpointChannelName.
        """
        circuits = {c.CircuitPosition: c for c in self.ZoneCallCircuits}
        for zone in self.Zones:
            primary = circuits.get(zone.PrimaryCircuitPosition)
            if primary is None or primary.ServesZone != zone.Name:
                raise ValueError(
                    f"Axiom 3 (PrimaryCircuit) failed: zone {zone.Name!r} names "
                    f"PrimaryCircuitPosition {zone.PrimaryCircuitPosition}, which is "
                    "not the position of a circuit serving it."
                )
            if primary.SetpointChannelName is None:
                raise ValueError(
                    f"Axiom 3 (PrimaryCircuit) failed: zone {zone.Name!r}'s primary "
                    f"circuit {primary.Name!r} carries no SetpointChannelName."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: CircuitDistinctness
        a. No two circuits SHALL share a Name. b. No two circuits SHALL
        share a WhitewireChannelName. c. No two circuits SHALL share a
        SetpointChannelName. d. No two circuits SHALL share a
        TempChannelName. e. No two circuits SHALL share a FailsafeRelayNode.
        f. No two circuits SHALL share an OpsRelayNode.
        """
        circuits = self.ZoneCallCircuits
        for field, values in (
            ("Name", [c.Name for c in circuits]),
            ("WhitewireChannelName", [c.WhitewireChannelName for c in circuits]),
            (
                "SetpointChannelName",
                [c.SetpointChannelName for c in circuits if c.SetpointChannelName is not None],
            ),
            (
                "TempChannelName",
                [c.TempChannelName for c in circuits if c.TempChannelName is not None],
            ),
            ("FailsafeRelayNode", [c.FailsafeRelayNode for c in circuits]),
            ("OpsRelayNode", [c.OpsRelayNode for c in circuits]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(
                    f"Axiom 4 (CircuitDistinctness) failed: {field} values {values} "
                    "are not distinct."
                )
        return self
