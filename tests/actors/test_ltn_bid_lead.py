"""The LTN's settings: the bid lead is seconds before the slot, inside one
slot."""

import pytest
from pydantic import ValidationError

from actors.ltn.config import LtnSettings
from actors.ltn.market import MARKET_SLOT_S


@pytest.fixture(autouse=True)
def no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LTN_BID_LEAD_S", raising=False)


def test_bid_lead_defaults_to_three_minutes() -> None:
    assert LtnSettings(_env_file=None).bid_lead_s == 180


def test_bid_lead_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LTN_BID_LEAD_S", "120")
    assert LtnSettings(_env_file=None).bid_lead_s == 120


@pytest.mark.parametrize("lead_s", [0, -1, MARKET_SLOT_S, MARKET_SLOT_S + 1])
def test_bid_lead_outside_one_slot_is_refused(lead_s: int) -> None:
    with pytest.raises(ValidationError):
        LtnSettings(_env_file=None, bid_lead_s=lead_s)
