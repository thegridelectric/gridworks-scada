from typing import List, Literal, Optional

from pydantic import ConfigDict, model_validator
from typing_extensions import Self

from gwsproto.enums import House0PrimaryFlowSource
from gwsproto.named_types.hvac_zone import HvacZone
from gwsproto.named_types.zone_call_circuit import ZoneCallCircuit
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class Hydronic(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/gw.hydronic/000
    """

    Zones: List[HvacZone]
    ZoneCallCircuits: Optional[List[ZoneCallCircuit]] = None
    TotalStoreTanks: int
    UseSiegLoop: bool
    SiegLoopPlumbed: bool
    PrimaryFlowSource: House0PrimaryFlowSource
    Strategy: str
    TypeName: Literal["gw.hydronic"] = "gw.hydronic"
    Version: Literal["000"] = "000"
    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: SiegLoopControlImpliesPlumbed
        If UseSiegLoop is true then SiegLoopPlumbed SHALL be true — the scada
        cannot run the Siegenthaler loop unless it is plumbed.
        """
        if self.UseSiegLoop and not self.SiegLoopPlumbed:
            raise ValueError(
                "Axiom 1 (SiegLoopControlImpliesPlumbed) failed: UseSiegLoop requires "
                "SiegLoopPlumbed to be true."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: Cardinality
        a. TotalStoreTanks SHALL be between 1 and 6 inclusive.
        b. The number of Zones SHALL be between 1 and 6 inclusive.
        """
        if not 1 <= self.TotalStoreTanks <= 6:
            raise ValueError(
                "Axiom 2 (Cardinality) failed: TotalStoreTanks "
                f"({self.TotalStoreTanks}) must be between 1 and 6 inclusive."
            )
        if not 1 <= len(self.Zones) <= 6:
            raise ValueError(
                "Axiom 2 (Cardinality) failed: number of Zones "
                f"({len(self.Zones)}) must be between 1 and 6 inclusive."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: CircuitResolution
        a. Every circuit's ServesZone SHALL equal the Name of a zone in
        Zones. b. No two circuits SHALL share a CircuitPosition.
        """
        circuits = self.ZoneCallCircuits or []
        zone_names = {z.Name for z in self.Zones}
        for c in circuits:
            if c.ServesZone not in zone_names:
                raise ValueError(
                    "Axiom 3 (CircuitResolution) failed: ServesZone "
                    f"{c.ServesZone!r} does not name a zone in Zones."
                )
        positions = [c.CircuitPosition for c in circuits]
        if len(positions) != len(set(positions)):
            raise ValueError(
                "Axiom 3 (CircuitResolution) failed: CircuitPosition values "
                f"{positions} are not distinct."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: LearnedNeedsTempChannel
        For every circuit whose SetpointSource is Learned, the zone named
        by its ServesZone SHALL carry a TempChannelName.
        """
        zones_by_name = {z.Name: z for z in self.Zones}
        for c in self.ZoneCallCircuits or []:
            zone = zones_by_name.get(c.ServesZone)
            if (
                c.SetpointSource == "Learned"
                and zone is not None
                and zone.TempChannelName is None
            ):
                raise ValueError(
                    "Axiom 4 (LearnedNeedsTempChannel) failed: circuit at "
                    f"position {c.CircuitPosition} is Learned but zone "
                    f"{c.ServesZone!r} has no TempChannelName."
                )
        return self
