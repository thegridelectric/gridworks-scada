"""The LTN sends the FLO's answer to its scada the way it sends the request:
a gw-wrapped copy over the scada broker, so the ear sees both sides of the
FLO boundary and the journal keeps them."""

from gwproto import Message

from actors.ltn.ltn import Ltn
from gwsproto.named_types import FloRecommendation
from tests.named_types.test_flo_recommendation import example


class Services:
    publication_name = "hw1.isone.me.versant.keene.oak.ltn"

    def __init__(self) -> None:
        self.published: list[tuple[str, Message]] = []

    def publish_message(self, client: str, message: Message, **kwargs) -> None:
        self.published.append((client, message))


class Logger:
    def path(self, *args, **kwargs) -> None:
        pass


class Node:
    name = "s"


def ltn_with_stubs(monkeypatch) -> tuple[Ltn, Services]:
    ltn = Ltn.__new__(Ltn)
    services = Services()
    ltn._services = services
    monkeypatch.setattr(Ltn, "logger", property(lambda self: Logger()))
    monkeypatch.setattr(Ltn, "scada", property(lambda self: Node()))
    return ltn, services


def test_the_recommendation_goes_to_the_scada(monkeypatch) -> None:
    ltn, services = ltn_with_stubs(monkeypatch)
    recommendation = FloRecommendation.model_validate(example())

    ltn.process_ltn_message(Message(Src="ltn", Dst="ltn", Payload=recommendation))

    assert ltn.recommendation == recommendation
    ((client, message),) = services.published
    assert client == Ltn.SCADA_MQTT
    assert message.Header.Dst == "s"
    assert message.Payload == recommendation
