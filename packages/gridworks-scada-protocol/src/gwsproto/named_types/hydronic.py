from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator
from typing_extensions import Self

from gwsproto.enums import House0PrimaryFlowSource
from gwsproto.named_types.hvac_zone import HvacZone
from gwsproto.named_types.zone_call_circuit import ZoneCallCircuit


class Hydronic(BaseModel):
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
