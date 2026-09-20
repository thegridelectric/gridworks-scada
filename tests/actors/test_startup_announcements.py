"""Once per run, when the upstream link can first carry a publish, a scada
sends its layout.lite and the home's ta.deed, or a no-ta-deed Warning when
it holds no deed. No LTN is needed for any of it."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from actors.scada import Scada
from gwproactor.config import Paths
from gwsproto.enums import LogLevel, TaValidationState
from gwsproto.named_types import Glitch, LayoutLite, TaDeed
from scada_app import ScadaApp
from tests.utils.scada_live_test_helper import ScadaLiveTest


def remove_deed() -> None:
    # The autouse fixture seeds a ValidatedSimulatedAsset deed.
    Path(Paths(name="scada").hardware_layout).parent.joinpath("ta-deed.json").unlink()


async def no_announcer(self: Scada) -> None:
    """Stands in for the announcer task, so a test's own call is the only
    send."""


def record_sends(monkeypatch: pytest.MonkeyPatch, scada: Scada) -> list[Any]:
    sent: list[Any] = []
    monkeypatch.setattr(
        scada, "_send_to", lambda to_node, payload, from_node=None: sent.append(payload)
    )
    return sent


@pytest.mark.asyncio
async def test_ta_deed_is_the_deed_and_validation_state_derives_from_it(
    request: pytest.FixtureRequest,
) -> None:
    async with ScadaLiveTest(request=request) as tst:
        app = tst.child1_app
        deed = app.ta_deed
        assert isinstance(deed, TaDeed)
        assert app.validation_state == deed.ValidationState
        assert app.validation_state != TaValidationState.UnValidated

        remove_deed()
        assert app.ta_deed is None
        assert app.validation_state == TaValidationState.UnValidated


@pytest.mark.asyncio
async def test_announcements_with_a_deed_are_the_layout_and_that_deed(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Scada, "announce_at_first_broker_link", no_announcer)
    async with ScadaLiveTest(request=request) as tst:
        tst.start_child1()
        scada = tst.child1_app.scada
        sent = record_sends(monkeypatch, scada)
        scada.send_startup_announcements()
        assert [type(p) for p in sent] == [LayoutLite, TaDeed]
        assert sent[0].FromGNodeAlias == scada.layout.scada_g_node_alias
        assert sent[1] == tst.child1_app.ta_deed


@pytest.mark.asyncio
async def test_announcements_with_no_deed_are_the_layout_and_one_warning(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    remove_deed()
    monkeypatch.setattr(Scada, "announce_at_first_broker_link", no_announcer)
    async with ScadaLiveTest(request=request) as tst:
        tst.start_child1()
        scada = tst.child1_app.scada
        sent = record_sends(monkeypatch, scada)
        logged: list[str] = []
        monkeypatch.setattr(scada, "log", logged.append)
        scada.send_startup_announcements()
        assert [type(p) for p in sent] == [LayoutLite, Glitch]
        assert [note for note in logged if note.startswith("Warning Glitch: no-ta-deed")]
        glitch = sent[1]
        assert isinstance(glitch, Glitch)
        assert glitch.Type == LogLevel.Warning
        assert glitch.Summary == "no-ta-deed"
        assert glitch.FromGNodeAlias == scada.layout.scada_g_node_alias


@pytest.mark.asyncio
async def test_announces_once_with_no_ltn_and_not_again_on_activation(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    link_active_at_call: list[bool] = []

    def count_call(self: Scada) -> None:
        link_active_at_call.append(tst.child_to_parent_link.active())

    monkeypatch.setattr(Scada, "send_startup_announcements", count_call)
    monkeypatch.setattr(Scada, "STARTUP_ANNOUNCE_POLL_S", 0.01)

    async with ScadaLiveTest(request=request) as tst:
        tst.start_child1()
        await tst.await_for(
            lambda: len(link_active_at_call) == 1,
            "ERROR waiting for the startup announcements with no LTN",
        )
        # Sent on the broker link alone: no peer had activated it.
        assert link_active_at_call == [False]

        tst.start_parent()
        await tst.await_for(
            lambda: tst.child_to_parent_link.active(),
            "ERROR waiting for scada to ltn link",
        )
        await asyncio.sleep(0.2)
        assert len(link_active_at_call) == 1


@pytest.mark.asyncio
async def test_nothing_is_announced_until_the_link_is_send_capable(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    send_capable = False

    monkeypatch.setattr(Scada, "send_startup_announcements", lambda self: calls.append(1))
    monkeypatch.setattr(Scada, "STARTUP_ANNOUNCE_POLL_S", 0.01)
    monkeypatch.setattr(ScadaApp, "upstream_is_send_capable", lambda self: send_capable)

    async with ScadaLiveTest(request=request) as tst:
        tst.start_child1()
        await asyncio.sleep(0.3)
        assert calls == []

        send_capable = True
        await tst.await_for(
            lambda: calls == [1],
            "ERROR waiting for the startup announcements",
        )
