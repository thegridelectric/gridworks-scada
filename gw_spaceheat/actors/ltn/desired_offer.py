"""The LTN's desired offer for a market slot: what it wants the slot's
contract to say, as the maker's price stages and the dispatch terms move
it. Persisted beside the contract heartbeat so a restart resumes the slot.
No sema word states it yet; `ltn.desired.offer` retires this record."""

from typing import Optional

from gwsproto.enums import PriceStage
from gwsproto.property_format import UTCSeconds
from pydantic import BaseModel, ConfigDict, NonNegativeInt


class DesiredOffer(BaseModel):
    """The Wh the LTN wants the slot's contract to hold, the stage of the
    price it was read at, the bid's reading at the Provisional (the offer
    the slot takes when no Final comes), whether the Final stage was
    reached by the deadline rather than a Final price, and the Wh of the
    one amendment sent, if any."""

    model_config = ConfigDict(extra="forbid")

    SlotStartS: UTCSeconds
    OfferWh: NonNegativeInt
    Stage: PriceStage
    ProvisionalReadingWh: NonNegativeInt
    NoFinal: bool = False
    AmendedToWh: Optional[NonNegativeInt] = None
