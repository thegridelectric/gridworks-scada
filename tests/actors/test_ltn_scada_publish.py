"""What the LTN copies to the scada is a word: the gw envelope takes its
MessageType from the payload's TypeName, so a payload without one is
refused when the message is built, never at publish."""

import pytest
from gwproto import Message
from pydantic import BaseModel, ValidationError

from gwsproto.named_types import FloNextHourPlans


class NotAWord(BaseModel):
    horizon: int = 48


def test_a_payload_without_a_type_name_is_refused_at_construction() -> None:
    with pytest.raises(ValidationError, match="MessageType"):
        Message(Src="ltn", Dst="s", Payload=NotAWord())


def test_a_word_wraps_under_its_own_type_name() -> None:
    plans = FloNextHourPlans(ExpectedStorageKwhAtHour1=12.5, ExpectedElecUsdMwhAtHour1=101.0, HourlyHpKwhElPlan=[3.0, 0.0])
    message = Message(Src="ltn", Dst="s", Payload=plans)
    assert message.Header.MessageType == "flo.next.hour.plans"
