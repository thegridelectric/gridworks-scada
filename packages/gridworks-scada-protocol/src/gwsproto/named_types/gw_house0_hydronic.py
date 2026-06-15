from typing import List, Literal

from pydantic import BaseModel, ConfigDict, model_validator
from typing_extensions import Self

from gwsproto.enums import GwHouse0PrimaryFlowSource
from gwsproto.named_types.gw1_hvac_zone import Gw1HvacZone


class GwHouse0Hydronic(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/gw.house0.hydronic/000

    The hydronic / flow-topology config of a House0-fleet layout: its heating
    zones, store-tank count, Siegenthaler-loop topology (plumbed? actively
    controlled?), how primary-loop flow is obtained, and the control strategy. The
    measured-vs-derived "primary-flow" choice is a physical-topology fact carried
    here so the layout states it rather than it being inferred from channel
    presence. Hand-ported from the gwta sema snapshot runtime (gw.house0.hydronic/000).
    """

    Zones: List[Gw1HvacZone]
    TotalStoreTanks: int
    UseSiegLoop: bool
    SiegLoopPlumbed: bool
    PrimaryFlowSource: GwHouse0PrimaryFlowSource
    Strategy: str
    TypeName: Literal["gw.house0.hydronic"] = "gw.house0.hydronic"
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
