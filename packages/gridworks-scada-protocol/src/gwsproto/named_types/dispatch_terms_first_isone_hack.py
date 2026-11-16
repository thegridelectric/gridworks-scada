from typing import Literal

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class DispatchTermsFirstIsoneHack(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/dispatch.terms.first.isone.hack/000"""

    MarketMakerAlias: Literal["hw1.isone.me.versant.keene"] = "hw1.isone.me.versant.keene"
    MarketProductName: Literal["rt60gate1"] = "rt60gate1"
    FinalDeadlineS: Literal[240] = 240
    AmendmentsAllowed: Literal[1] = 1
    BindingStage: Literal["Final"] = "Final"
    ProvisionalAction: Literal["ReduceOnly"] = "ReduceOnly"
    TypeName: Literal["dispatch.terms.first.isone.hack"] = "dispatch.terms.first.isone.hack"
    Version: Literal["000"] = "000"
