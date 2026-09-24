"""A pico post the actor refuses (a params version it does not take, text it
cannot decode, a body it cannot read, or a pico the layout does not name)
is a field condition: one Warning glitch per pico and condition per day,
never a problem event. The web handler runs on the IO loop, so the glitch
reaches the actor through send_threadsafe and the actor sends it on."""
import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from gwproto import Message

from actors.api_btu_meter import ApiBtuMeter
from actors.api_flow_module import ApiFlowModule
from actors.api_tank_module import ApiTankModule
from actors.pico_post_refusal import REFUSED_POST_REPORT_S
from gwsproto.enums import LogLevel
from gwsproto.named_types import Glitch
from tests.actors.test_pico_identity import (
    LAYOUT_BOARD,
    PAIRS,
    Post,
    boot,
    btu_params,
    capture_sends,
    capture_threadsafe,
    flow_params,
    tank_params,
    with_hall_flow_pico,
    with_real_pico,
)

HOUSE0_PAIRS = ["orange", "willow"]


class RawPost:
    """A post whose body is sent as given, not as JSON."""

    def __init__(self, text: str) -> None:
        self.body = text

    async def text(self) -> str:
        return self.body


class UnreadablePost:
    """A post whose body cannot be read."""

    async def text(self) -> str:
        raise ConnectionResetError("peer closed the connection")


def glitches(queued: list[Message]) -> list[Glitch]:
    """Every queued payload is a Warning glitch; return them."""
    payloads = [m.Payload for m in queued]
    assert all(isinstance(p, Glitch) and p.Type == LogLevel.Warning for p in payloads), payloads
    return payloads


def tank_actor(tmp_path: Path) -> ApiTankModule:
    pair = PAIRS["nolan"]
    app = boot(tmp_path, pair, with_real_pico(pair, "tank1", "PicoHwUid"))
    actor = app.get_communicator_as_type("tank1", ApiTankModule)
    assert actor is not None
    return actor


def btu_actor(tmp_path: Path) -> ApiBtuMeter:
    pair = PAIRS["nolan"]
    app = boot(tmp_path, pair, with_real_pico(pair, "primary-btu", "HwUid"))
    actor = app.get_communicator_as_type("primary-btu", ApiBtuMeter)
    assert actor is not None
    return actor


def flow_actor(tmp_path: Path, pair_name: str) -> ApiFlowModule:
    pair = PAIRS[pair_name]
    app = boot(tmp_path, pair, with_hall_flow_pico(pair))
    actor = app.get_communicator_as_type("dist-flow", ApiFlowModule)
    assert actor is not None
    return actor


def tank_110_post() -> dict:
    body = tank_params(LAYOUT_BOARD).model_dump(mode="json")
    del body["PicoBoardVariant"]
    del body["MicropythonVersion"]
    body["Version"] = "110"
    return body


def test_tank_module_warns_once_a_day_on_a_params_version_it_does_not_take(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = tank_actor(tmp_path)
    queued = capture_threadsafe(actor)

    for _ in range(2):
        asyncio.run(actor._handle_params_post(Post(tank_110_post())))
    [glitch] = glitches(queued)
    assert glitch.Summary == "params-version"
    assert "pico_1a2b3c" in glitch.Details
    assert "tank.module.params 110" in glitch.Details
    assert "200" in glitch.Details

    a_day_on = time.time() + REFUSED_POST_REPORT_S
    monkeypatch.setattr(time, "time", lambda: a_day_on)
    asyncio.run(actor._handle_params_post(Post(tank_110_post())))
    assert len(glitches(queued)) == 2


def test_tank_module_warns_once_on_a_post_it_cannot_decode(tmp_path: Path) -> None:
    actor = tank_actor(tmp_path)
    queued = capture_threadsafe(actor)

    for _ in range(2):
        asyncio.run(actor._handle_params_post(RawPost("{not json")))
        asyncio.run(actor._handle_microvolts_post(RawPost("{not json")))
    [glitch] = glitches(queued)
    assert glitch.Summary == "refused-post"


def test_tank_module_warns_once_on_a_post_it_cannot_read(tmp_path: Path) -> None:
    actor = tank_actor(tmp_path)
    queued = capture_threadsafe(actor)

    for _ in range(2):
        asyncio.run(actor._handle_params_post(UnreadablePost()))
    [glitch] = glitches(queued)
    assert glitch.Summary == "unreadable-post"


def test_tank_module_warns_once_on_a_pico_the_layout_does_not_name(tmp_path: Path) -> None:
    actor = tank_actor(tmp_path)
    queued = capture_threadsafe(actor)
    stranger = tank_params(LAYOUT_BOARD).model_copy(update={"HwUid": "pico_ffffff"})

    for _ in range(2):
        asyncio.run(actor._handle_params_post(Post(stranger.model_dump(mode="json"))))
    [glitch] = glitches(queued)
    assert glitch.Summary == "unknown-pico"
    assert "pico_ffffff" in glitch.Details


def test_btu_meter_warns_once_on_a_params_version_it_does_not_take(tmp_path: Path) -> None:
    actor = btu_actor(tmp_path)
    queued = capture_threadsafe(actor)
    body = btu_params(actor, LAYOUT_BOARD).model_dump(mode="json")
    body["Version"] = "999"

    for _ in range(2):
        asyncio.run(actor._handle_async_btu_params_post(Post(body)))
    [glitch] = glitches(queued)
    assert glitch.Summary == "params-version"
    assert "async.btu.params 999" in glitch.Details


def test_btu_meter_warns_once_on_a_pico_the_layout_does_not_name(tmp_path: Path) -> None:
    actor = btu_actor(tmp_path)
    queued = capture_threadsafe(actor)
    stranger = btu_params(actor, LAYOUT_BOARD).model_copy(update={"HwUid": "pico_ffffff"})

    for _ in range(2):
        asyncio.run(actor._handle_async_btu_params_post(Post(stranger.model_dump(mode="json"))))
    [glitch] = glitches(queued)
    assert glitch.Summary == "unknown-pico"
    assert "pico_ffffff" in glitch.Details


@pytest.mark.parametrize("pair_name", HOUSE0_PAIRS)
def test_flow_module_warns_once_on_a_post_it_cannot_decode(tmp_path: Path, pair_name: str) -> None:
    actor = flow_actor(tmp_path, pair_name)
    queued = capture_threadsafe(actor)

    for _ in range(2):
        asyncio.run(actor._handle_hall_params_post(RawPost("{not json")))
    [glitch] = glitches(queued)
    assert glitch.Summary == "refused-post"


@pytest.mark.parametrize("pair_name", HOUSE0_PAIRS)
def test_flow_module_warns_once_on_a_pico_the_layout_does_not_name(
    tmp_path: Path, pair_name: str
) -> None:
    actor = flow_actor(tmp_path, pair_name)
    queued = capture_threadsafe(actor)
    stranger = flow_params(LAYOUT_BOARD).model_copy(update={"HwUid": "pico_ffffff"})

    for _ in range(2):
        asyncio.run(actor._handle_hall_params_post(Post(stranger.model_dump(mode="json"))))
    [glitch] = glitches(queued)
    assert glitch.Summary == "unknown-pico"
    assert "pico_ffffff" in glitch.Details


@pytest.mark.parametrize("make_actor", [tank_actor, btu_actor, lambda p: flow_actor(p, "willow")])
def test_the_actor_sends_a_queued_glitch_on(tmp_path: Path, make_actor: Any) -> None:
    actor = make_actor(tmp_path)
    sent = capture_sends(actor)
    glitch = Glitch(
        FromGNodeAlias=actor.layout.scada_g_node_alias,
        Node=actor.name,
        Type=LogLevel.Warning,
        Summary="refused-post",
        Details="",
    )

    actor.process_message(Message(Src=actor.name, Dst=actor.name, Payload=glitch))
    assert sent == [glitch]


def test_btu_meter_warns_once_on_a_snapshot_it_cannot_decode(tmp_path: Path) -> None:
    actor = btu_actor(tmp_path)
    queued = capture_threadsafe(actor)

    for _ in range(2):
        asyncio.run(actor._handle_multichannel_snapshot_post(Post({"HwUid": "pico_1a2b3c"})))
    [glitch] = glitches(queued)
    assert glitch.Summary == "refused-post"
