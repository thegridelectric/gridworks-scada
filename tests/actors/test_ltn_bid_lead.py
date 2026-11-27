"""The LTN's settings: the bid lead is seconds before the slot, inside one
slot, and the price forecast route is the price service's read URL."""

import pytest
from pydantic import ValidationError

from actors.ltn.config import LtnSettings
from actors.ltn.market import MARKET_SLOT_S


@pytest.fixture(autouse=True)
def no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LTN_BID_LEAD_S", raising=False)
    monkeypatch.delenv("LTN_PRICE_FORECAST_URL", raising=False)


def test_bid_lead_defaults_to_minute_55() -> None:
    assert LtnSettings(_env_file=None).bid_lead_s == 300


def test_bid_lead_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LTN_BID_LEAD_S", "120")
    assert LtnSettings(_env_file=None).bid_lead_s == 120


@pytest.mark.parametrize("lead_s", [0, -1, MARKET_SLOT_S, MARKET_SLOT_S + 1])
def test_bid_lead_outside_one_slot_is_refused(lead_s: int) -> None:
    with pytest.raises(ValidationError):
        LtnSettings(_env_file=None, bid_lead_s=lead_s)


PRICE_SERVICE = (
    "https://price-service.electricity.works/hw1-isone-me-versant-keene-ps/gw0-price-forecast"
)


def test_price_forecast_url_defaults_to_the_price_service() -> None:
    assert LtnSettings(_env_file=None).price_forecast_url == PRICE_SERVICE


def test_price_forecast_url_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LTN_PRICE_FORECAST_URL", "http://localhost:8080/gw0-price-forecast")
    assert LtnSettings(_env_file=None).price_forecast_url == "http://localhost:8080/gw0-price-forecast"
