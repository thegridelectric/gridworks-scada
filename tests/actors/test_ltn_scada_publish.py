"""What the LTN copies to the scada is a word: the gw envelope takes its
MessageType from the payload's TypeName, so a payload without one is
refused when the message is built, never at publish."""

import pytest
from gwproto import Message
from pydantic import BaseModel, ValidationError

from gwsproto.enums import MarketPriceUnit, MarketQuantityUnit
from gwsproto.named_types import FloOptimalPath, FloPreviousRun, PriceQuantityUnitless


class NotAWord(BaseModel):
    horizon: int = 48


def test_a_payload_without_a_type_name_is_refused_at_construction() -> None:
    with pytest.raises(ValidationError, match="MessageType"):
        Message(Src="ltn", Dst="s", Payload=NotAWord())


def test_a_word_wraps_under_its_own_type_name() -> None:
    plans = FloOptimalPath(StartUnixS=1762009200, StepDurationMinutes=[60, 60], HpAvgWList=[3000, 0], StoreWhList=[38500, 31200])
    message = Message(Src="ltn", Dst="s", Payload=plans)
    assert message.Header.MessageType == "flo.optimal.path"


def test_the_cleared_run_wraps_as_flo_previous_run() -> None:
    run = FloPreviousRun(
        Path=FloOptimalPath(StartUnixS=1762009200, StepDurationMinutes=[60, 60], HpAvgWList=[3000, 0], StoreWhList=[38500, 31200]),
        ClearedPairIndex=1,
        ClearedPair=PriceQuantityUnitless(PriceX1000=150000, QuantityX1000=3000),
        PriceUnit=MarketPriceUnit.USDPerMWh,
        QuantityUnit=MarketQuantityUnit.AvgkW,
        NextSlotPriceX1000=142500,
        CreatedMs=1762009260000,
    )
    message = Message(Src="ltn", Dst="s", Payload=run)
    assert message.Header.MessageType == "flo.previous.run"
