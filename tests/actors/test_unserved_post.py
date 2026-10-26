"""A POST to the scada's web server that no actor serves (a pico of a kind
the layout does not say, a pico identifying as a node the layout does not
name) is a field condition the box can only learn once the pico posts:
one Warning glitch per path per day, with the posted identity in the
details, and a log line on every post. The catch-all route is registered
last, after every actor's routes."""
import asyncio
import json
import time
from pathlib import Path

import pytest
from gwproto import Message

from actors.glitch_limit import REPEAT_GLITCH_S
from actors.unserved_post import UNSERVED_POST_PATH
from gwsproto.enums import LogLevel
from gwsproto.named_types import Glitch
from scada_app import ScadaApp
from tests.actors.test_pico_identity import PAIRS, boot, with_hall_flow_pico

HOUSE0_PAIRS = ["orange", "willow"]


class UnservedPost:
    """A pico's HTTP post to a path no actor serves."""

    def __init__(self, path: str, body: dict | str) -> None:
        self.path = path
        self.method = "POST"
        self.body = body if isinstance(body, str) else json.dumps(body)

    async def text(self) -> str:
        return self.body


def hall_flow_app(tmp_path: Path, pair_name: str) -> ScadaApp:
    pair = PAIRS[pair_name]
    return boot(tmp_path, pair, with_hall_flow_pico(pair))


def glitches(queued: list[Message]) -> list[Glitch]:
    payloads = [m.Payload for m in queued]
    assert all(isinstance(p, Glitch) and p.Type == LogLevel.Warning for p in payloads), payloads
    return payloads


@pytest.mark.parametrize("pair_name", HOUSE0_PAIRS)
def test_the_catch_all_is_the_last_post_route(tmp_path: Path, pair_name: str) -> None:
    app = hall_flow_app(tmp_path, pair_name)
    [routes] = app.get_web_server_route_strings().values()
    assert UNSERVED_POST_PATH in routes[-1]
    assert "/dist-flow/flow-hall-params" in " ".join(routes[:-1])


@pytest.mark.parametrize("pair_name", HOUSE0_PAIRS)
def test_a_reed_post_to_a_hall_node_is_one_warning_glitch_a_day(
    tmp_path: Path, pair_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = hall_flow_app(tmp_path, pair_name)
    queued: list[Message] = []
    app.raw_proactor.send_threadsafe = queued.append
    post = UnservedPost(
        "/dist-flow/flow-reed-params",
        {"HwUid": "pico_1a2b3c", "TypeName": "flow.reed.params", "Version": "101"},
    )

    for _ in range(2):
        asyncio.run(app.unserved_posts.handle(post))
    [glitch] = glitches(queued)
    assert glitch.Summary == "unserved-post"
    assert "/dist-flow/flow-reed-params" in glitch.Details
    assert "pico_1a2b3c" in glitch.Details
    assert "flow.reed.params" in glitch.Details

    a_day_on = time.time() + REPEAT_GLITCH_S
    monkeypatch.setattr(time, "time", lambda: a_day_on)
    asyncio.run(app.unserved_posts.handle(post))
    assert len(glitches(queued)) == 2


def test_a_post_the_layout_names_no_node_for_is_reported_by_path(tmp_path: Path) -> None:
    app = hall_flow_app(tmp_path, "willow")
    queued: list[Message] = []
    app.raw_proactor.send_threadsafe = queued.append

    asyncio.run(app.unserved_posts.handle(UnservedPost("/dist2-flow/flow-hall-params", "{not json")))
    [glitch] = glitches(queued)
    assert "/dist2-flow/flow-hall-params" in glitch.Details
    assert "pico_" not in glitch.Details
