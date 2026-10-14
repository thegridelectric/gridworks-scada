"""The live-test harness itself: a test scada does not depend on what else
listens on the laptop, and a stopped scada's failure dump says why."""

import asyncio
import socket
from pathlib import Path

import pytest
from gwproactor.message import ShutdownMessage

from gwsproto.data_classes.components.web_server_component import WebServerComponent
from sema_to_dc import load_layout
from tests.utils.scada_live_test_helper import ScadaLiveTest

CONFIG = Path(__file__).parent.parent / "config"


def declared_web_ports() -> list[int]:
    """The ports the default fixture layout declares for the scada's web servers."""
    layout = load_layout(CONFIG / "gw.nolan.layout.json", CONFIG / "gw.nolan.operational.params.json")
    return [ws.web_server_gt.Port for ws in layout.get_components_by_type(WebServerComponent)]


@pytest.mark.asyncio
async def test_a_scada_boots_while_its_declared_web_port_is_held(
    request: pytest.FixtureRequest,
) -> None:
    """With every port the fixture layout declares held by this test, the
    scada boots, its links come up and stay up, and it generates no
    shutdown or problem event."""
    ports = declared_web_ports()
    assert ports, "the fixture layout declares no web server; nothing to hold"
    holders: list[socket.socket] = []
    for port in ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("0.0.0.0", port))
            s.listen(1)
            holders.append(s)
        except OSError:
            s.close()  # something else already holds it, which serves the same purpose
    try:
        async with ScadaLiveTest(start_all=True, request=request) as h:
            await h.await_quiescent_connections()
            await asyncio.sleep(2)
            assert h.child_to_parent_link.active()
            assert h.child.recorded_events == []
    finally:
        for s in holders:
            s.close()


@pytest.mark.asyncio
async def test_the_dump_names_a_stopped_scadas_reason(
    request: pytest.FixtureRequest,
) -> None:
    reason = "held open for the harness test"
    async with ScadaLiveTest(start_all=True, request=request) as h:
        await h.await_quiescent_connections()
        h.child.send_threadsafe(ShutdownMessage(Src=h.child.name, Reason=reason))
        await h.await_for(
            lambda: reason in h.summary_str(),
            "ERROR waiting for the dump to name the shutdown reason",
        )
