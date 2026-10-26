"""An actor that raises on a message does not take the scada down. The
scada's in-process dispatch catches the raise, logs it and sends an Error
glitch to the LTN; the scada keeps serving messages. The allies do not
swallow their own raises: a contract whose handling fails is loud."""

import asyncio
from pathlib import Path

import pytest

from gwsproto.enums import LogLevel, SlowDispatchContractStatus
from gwsproto.named_types import Glitch, GoDormant, SlowDispatchContract
from gwsproto.names.core.node_names import CoreNodeNames
from sema_to_dc import load_layout
from tests.actors.test_ally_initialize import (
    CONFIG,
    DORMANT,
    MODES,
    WILLOW,
    in_local_control,
    mode_ops,
    quick_allies,
)
from tests.actors.test_operating_status import ltn_hb
from tests.actors.test_startup_contract_load import Sends, leaf_ally, live_contract
from tests.utils.scada_live_test_helper import ScadaLiveTest, fresh_buffer


class ColdZoneLookupFailed(RuntimeError):
    ...


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", sorted(MODES), ids=sorted(MODES))
async def test_an_ally_that_raises_on_a_contract_is_reported_and_the_scada_keeps_running(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    ops_path = mode_ops(tmp_path, MODES[mode])
    layout = load_layout(CONFIG / WILLOW[0], ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        quick_allies(monkeypatch)
        h.start_child1()
        scada = h.child1_app.scada
        ally = leaf_ally(scada)
        await in_local_control(h, scada)
        sends = Sends(monkeypatch, scada)
        fresh_buffer(scada)

        def failing_wake_up(*args, **kwargs):
            raise ColdZoneLookupFailed("no zone is cold enough to look up")

        monkeypatch.setattr(ally._impl, "wake_up", failing_wake_up)
        scada.process_scada_message(
            scada.ltn, ltn_hb(scada, live_contract(scada), SlowDispatchContractStatus.Created)
        )

        await h.await_for(
            lambda: any(
                to == CoreNodeNames.ltn and isinstance(p, Glitch) and p.Type == LogLevel.Error
                for to, p in sends.sent
            ),
            "ERROR waiting for the Error glitch",
            timeout=10,
            err_str_f=lambda: f"sent: {[(to, type(p).__name__) for to, p in sends.sent]}",
        )
        errors = [p for to, p in sends.sent if to == CoreNodeNames.ltn and isinstance(p, Glitch)]
        assert len(errors) == 1
        glitch = errors[0]
        assert glitch.Node == CoreNodeNames.leaf_ally
        assert glitch.Summary == "actor-raised"
        assert SlowDispatchContract.__name__ in glitch.Details
        assert ColdZoneLookupFailed.__name__ in glitch.Details

        # The scada is still serving messages: the ally takes the next one.
        scada._send_to(scada.leaf_ally, GoDormant(ToName=scada.leaf_ally.name))
        await h.await_for(
            lambda: ally.state in DORMANT,
            "ERROR waiting for the ally to take a message after the raise",
            timeout=10,
            err_str_f=lambda: f"ally state: {ally.state}",
        )
        assert any(t.get_name() == "scada top_state_tracker" for t in asyncio.all_tasks())
