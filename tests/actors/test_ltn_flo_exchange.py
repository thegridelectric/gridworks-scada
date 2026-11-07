"""The LTN's exchange with the FLO over the scada broker: the request goes
out gw-wrapped to the flo class with a copy to the scada, and the answer
that matches the request held becomes the bid to the maker, with a copy
to the scada so the ear sees both sides of the FLO boundary."""

import copy

import pytest
from gwproto import Message

from actors.ltn.flo_service import FLO_DST, flo_alias, flo_recommendation_topic
from actors.ltn.ltn import Ltn
from actors.ltn.market import market_slot_name
from clock import WallClock
from gwsproto.named_types import Bid, FloParams, FloRecommendation
from tests.actors.test_flo_request import ALIAS, START_S, build, ops
from tests.named_types.test_flo_recommendation import example


class Services:
    publication_name = ALIAS + ".ltn"

    def __init__(self) -> None:
        self.published: list[tuple[str, Message]] = []

    def publish_message(self, client: str, message: Message, **kwargs) -> None:
        self.published.append((client, message))


class Logger:
    def path(self, *args, **kwargs) -> None:
        pass


class Node:
    name = "s"


class ContractHandler:
    latest_bid: Bid | None = None


def ltn_with_stubs(monkeypatch: pytest.MonkeyPatch) -> tuple[Ltn, Services]:
    ltn = Ltn.__new__(Ltn)
    services = Services()
    ltn._services = services
    ltn.flo_params = None
    ltn.recommendation = None
    ltn.contract_handler = ContractHandler()
    monkeypatch.setattr(Ltn, "logger", property(lambda self: Logger()))
    monkeypatch.setattr(Ltn, "scada", property(lambda self: Node()))
    monkeypatch.setattr(Ltn, "ops", property(lambda self: ops()))
    monkeypatch.setattr(Ltn, "plant_clock", property(lambda self: WallClock()))
    monkeypatch.setattr(Ltn, "log", lambda self, note: None)
    return ltn, services


def answer(params: FloParams) -> FloRecommendation:
    """The FLO's answer to `params`."""
    d = copy.deepcopy(example())
    d["BidderAlias"] = params.GNodeAlias
    for path in d["OptimalPathList"]:
        path["StartUnixS"] = params.StartUnixS
    return FloRecommendation.model_validate(d)


def test_the_flo_is_the_universes() -> None:
    assert flo_alias("hw1.isone.me.versant.keene.oak") == "hw1.flo"
    assert flo_alias(ALIAS) == "d1.flo"
    assert flo_recommendation_topic("hw1.flo") == "gw/hw1-flo/to/ltn/flo-recommendation"


def test_the_request_goes_to_the_flo_and_the_scada(monkeypatch: pytest.MonkeyPatch) -> None:
    ltn, services = ltn_with_stubs(monkeypatch)
    params = build()

    ltn.send_flo_params(params)

    (scada_client, to_scada), (flo_client, to_flo) = services.published
    assert scada_client == flo_client == Ltn.SCADA_MQTT
    assert to_scada.Header.Dst == "s"
    assert to_scada.Payload == params
    assert to_flo.Header.Src == services.publication_name
    assert to_flo.Header.Dst == FLO_DST
    assert to_flo.Payload == params
    assert to_flo.mqtt_topic() == f"gw/{services.publication_name.replace('.', '-')}/to/flo/flo-params"


def test_the_answer_becomes_the_bid(monkeypatch: pytest.MonkeyPatch) -> None:
    ltn, services = ltn_with_stubs(monkeypatch)
    ltn.flo_params = build()
    recommendation = answer(ltn.flo_params)

    ltn.process_flo_recommendation(recommendation)

    assert ltn.recommendation == recommendation
    (_, to_scada), (_, to_maker) = services.published
    assert to_scada.Header.Dst == "s"
    assert to_scada.Payload == recommendation
    assert to_maker.Header.Dst == "mm"
    bid = to_maker.Payload
    assert isinstance(bid, Bid)
    assert ltn.contract_handler.latest_bid == bid
    assert bid.BidderAlias == ALIAS
    assert bid.MarketSlotName == market_slot_name(ops(), START_S)
    assert bid.PqPairs == recommendation.PqPairs


@pytest.mark.parametrize(
    "change",
    [
        {"BidderAlias": "d1.isone.ct.newhaven.willow2"},
        {"StartUnixS": START_S + 3600},
    ],
    ids=["another bidder", "another slot"],
)
def test_an_answer_to_another_request_is_dropped(monkeypatch: pytest.MonkeyPatch, change: dict) -> None:
    ltn, services = ltn_with_stubs(monkeypatch)
    ltn.flo_params = build()
    other = build(g_node_alias=change.get("BidderAlias", ALIAS), start_unix_s=change.get("StartUnixS", START_S))

    ltn.process_flo_recommendation(answer(other))

    assert ltn.recommendation is None
    assert ltn.contract_handler.latest_bid is None
    assert services.published == []


def test_an_answer_with_no_request_held_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    ltn, services = ltn_with_stubs(monkeypatch)

    ltn.process_flo_recommendation(answer(build()))

    assert ltn.recommendation is None
    assert services.published == []


def test_a_second_answer_to_the_same_request_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    ltn, services = ltn_with_stubs(monkeypatch)
    ltn.flo_params = build()
    recommendation = answer(ltn.flo_params)

    ltn.process_flo_recommendation(recommendation)
    ltn.process_flo_recommendation(recommendation)

    assert len(services.published) == 2
