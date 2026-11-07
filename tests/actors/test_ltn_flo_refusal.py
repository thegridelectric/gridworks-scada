"""The LTN hears the FLO's flo.refusal: the one for the request held is
copied to the scada and raised as a Warning glitch, so the fleet sees why
the slot has no FLO bid; one for another request is dropped. The LTN's
bid is untouched either way."""

import pytest
from gwproto import Message

from actors.ltn.flo_service import flo_refusal_topic
from actors.ltn.ltn import Ltn
from gwsproto.enums import FloRefusalReason, LogLevel
from gwsproto.named_types import FloRefusal, Glitch
from tests.actors.test_flo_request import ALIAS, START_S, build
from tests.actors.test_ltn_flo_exchange import Services, ltn_with_stubs


class Layout:
    ltn_g_node_alias = ALIAS + ".ltn"


class LtnNode:
    name = "ltn"


class ServicesWithLoop(Services):
    """The glitch goes to the LTN itself and comes out to the scada."""

    def __init__(self, ltn: Ltn) -> None:
        super().__init__()
        self.ltn = ltn

    def send_threadsafe(self, message: Message) -> None:
        self.ltn.process_ltn_message(message)


def ltn_hearing_refusals(monkeypatch: pytest.MonkeyPatch) -> tuple[Ltn, Services]:
    ltn, _ = ltn_with_stubs(monkeypatch)
    services = ServicesWithLoop(ltn)
    ltn._services = services
    monkeypatch.setattr(Ltn, "layout", property(lambda self: Layout()))
    monkeypatch.setattr(Ltn, "node", property(lambda self: LtnNode()))
    monkeypatch.setattr(Ltn, "name", property(lambda self: "ltn"))
    return ltn, services


def refusal(**overrides) -> FloRefusal:
    d = {
        "BidderAlias": ALIAS,
        "StartUnixS": START_S,
        "Reason": "NoMatrix",
        "Detail": "No cached transition matrix",
        "CreatedMs": START_S * 1000,
    }
    d.update(overrides)
    return FloRefusal.model_validate(d)


def test_the_refusal_topic() -> None:
    assert flo_refusal_topic("hw1.flo") == "gw/hw1-flo/to/ltn/flo-refusal"


def test_a_refusal_of_the_request_held_is_recorded_and_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    ltn, services = ltn_hearing_refusals(monkeypatch)
    ltn.flo_params = build()

    ltn.process_flo_refusal(refusal())

    (_, to_scada), (_, glitch_to_scada) = services.published
    assert to_scada.Header.Dst == "s"
    assert to_scada.Payload == refusal()
    glitch = glitch_to_scada.Payload
    assert isinstance(glitch, Glitch)
    assert glitch.Type == LogLevel.Warning
    assert glitch.Summary == f"FLO refused slot {START_S}: {FloRefusalReason.NoMatrix.value}"
    assert glitch.Details == "No cached transition matrix"
    assert ltn.recommendation is None
    assert ltn.contract_handler.latest_bid is None


@pytest.mark.parametrize(
    "change",
    [
        {"BidderAlias": "d1.isone.ct.newhaven.willow2"},
        {"StartUnixS": START_S + 3600},
    ],
    ids=["another bidder", "another slot"],
)
def test_a_refusal_of_another_request_is_dropped(monkeypatch: pytest.MonkeyPatch, change: dict) -> None:
    ltn, services = ltn_hearing_refusals(monkeypatch)
    ltn.flo_params = build()

    ltn.process_flo_refusal(refusal(**change))

    assert services.published == []


def test_a_refusal_with_no_request_held_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    ltn, services = ltn_hearing_refusals(monkeypatch)

    ltn.process_flo_refusal(refusal())

    assert services.published == []
