"""The scada's posture is its layout.lite and its operating status, the two
things the LTN needs before it can act with the scada. The posture goes out
whenever the upstream link activates and in answer to the LTN's send.layout,
with the status sent whether or not it has changed. An LTN that restarts
inside one ping period is never seen by the scada's link state, so its
send.layout on boot is what brings the status back. A send.layout from the
admin is answered with the layout alone."""

import time
from typing import Any

import pytest

from actors.scada import Scada
from gwsproto.named_types import HouseOperatingStatus, LayoutLite, SendLayout
from tests.utils.scada_live_test_helper import ScadaLiveTest


async def no_announcer(self: Scada) -> None:
    """Stands in for the startup announcer task, so a test's own call is
    the only send."""


def record_sends(monkeypatch: pytest.MonkeyPatch, scada: Scada) -> list[Any]:
    sent: list[Any] = []
    monkeypatch.setattr(
        scada, "_send_to", lambda to_node, payload, from_node=None: sent.append(payload)
    )
    return sent


def send_layout(scada: Scada) -> SendLayout:
    return SendLayout(
        FromGNodeAlias=scada.layout.ltn_g_node_alias,
        MessageCreatedMs=int(time.time() * 1000),
    )


@pytest.mark.asyncio
async def test_posture_is_the_layout_and_the_status_whether_or_not_changed(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Scada, "announce_at_first_broker_link", no_announcer)
    async with ScadaLiveTest(request=request) as tst:
        tst.start_child1()
        scada = tst.child1_app.scada
        sent = record_sends(monkeypatch, scada)
        scada.announce_posture()
        scada.report_operating_status()  # nothing changed: sends nothing
        scada.announce_posture()
        assert [type(p) for p in sent] == [
            LayoutLite, HouseOperatingStatus, LayoutLite, HouseOperatingStatus
        ]
        assert sent[0].FromGNodeAlias == scada.layout.scada_g_node_alias
        assert scada.last_operating_status == sent[3]


@pytest.mark.asyncio
async def test_the_ltns_send_layout_is_answered_with_the_posture(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Scada, "announce_at_first_broker_link", no_announcer)
    async with ScadaLiveTest(request=request) as tst:
        tst.start_child1()
        scada = tst.child1_app.scada
        sent = record_sends(monkeypatch, scada)
        scada.process_scada_message(scada.ltn, send_layout(scada))
        assert [type(p) for p in sent] == [LayoutLite, HouseOperatingStatus]
        sent.clear()
        scada.process_scada_message(scada.admin, send_layout(scada))
        assert [type(p) for p in sent] == [LayoutLite]


@pytest.mark.asyncio
async def test_posture_is_announced_when_the_upstream_link_activates(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    announced: list[bool] = []
    monkeypatch.setattr(
        Scada, "announce_posture", lambda self: announced.append(tst.child_to_parent_link.active())
    )
    monkeypatch.setattr(Scada, "announce_at_first_broker_link", no_announcer)
    async with ScadaLiveTest(request=request) as tst:
        tst.start_child1()
        tst.start_parent()
        await tst.await_for(
            lambda: len(announced) == 1,
            "ERROR waiting for the posture announcement on link activation",
        )
        assert announced == [True]
