from typing import Literal
from sema_snapshot.sema.base import SemaType


class DispatchTermsFirstIsoneHack(SemaType):
    """Sema: https://schemas.electricity.works/types/dispatch.terms.first.isone.hack/000"""

    market_maker_alias: Literal["hw1.isone.me.versant.keene"] = (
        "hw1.isone.me.versant.keene"
    )
    market_product_name: Literal["rt60gate1"] = "rt60gate1"
    final_deadline_s: Literal[240] = 240
    amendments_allowed: Literal[1] = 1
    binding_stage: Literal["Final"] = "Final"
    provisional_action: Literal["ReduceOnly"] = "ReduceOnly"
    type_name: Literal["dispatch.terms.first.isone.hack"] = (
        "dispatch.terms.first.isone.hack"
    )
    version: Literal["000"] = "000"
