"""The scada's command-tree builders emit trees that satisfy new.command.tree
axiom 1 (PrefixClosedHandles), for every boss the scada hands control to, on
both authored pairs.

`NewCommandTree` now enforces the axiom at construction, so an orphan-prefix
handle assignment fails here instead of going on the wire and being dropped by
the consumer's decode."""

from pathlib import Path

import pytest

from gwsproto.data_classes.house_0_names import H0N
from actors.pico_cycler import PicoCycler
from gwsproto.enums import ChangeRelayState, MainAutoEvent
from gwsproto.named_types import FsmEvent, GoDormant, NewCommandTree, PicoMissing
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
    "house0": ("gw.house0.layout.json", "gw.house0.operational.params.json"),
    "house0-sim": (
        "gw.house0.sim.layout.json",
        "gw.house0.sim.operational.params.json",
    ),
}


@pytest.fixture(params=sorted(PAIRS))
def app(request: pytest.FixtureRequest) -> ScadaApp:
    layout, ops = PAIRS[request.param]
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


def capture(scada) -> list:
    sent: list = []
    scada._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    return sent


@pytest.mark.parametrize("boss", ["admin", "local_control", "leaf_ally"])
def test_scada_command_tree_is_prefix_closed(app: ScadaApp, boss: str) -> None:
    scada = app.scada
    sent = capture(scada)
    scada.set_command_tree(getattr(scada, boss))
    trees = [p for _, p in sent if isinstance(p, NewCommandTree)]
    assert len(trees) == 1
    # Construction already ran axiom 1; re-validate the wire form explicitly.
    NewCommandTree.model_validate(trees[0].model_dump(by_alias=True, exclude_none=True))


@pytest.mark.parametrize("boss", ["admin", "local_control", "leaf_ally"])
def test_pico_cycler_keeps_vdc_relay_under_every_boss(app: ScadaApp, boss: str) -> None:
    """An interior node keeps its subtree: five-v-boss hangs under the
    tree's root (admin, or auto) with the pico-cycler and vdc-relay under
    it, whoever the boss is; every other actuator reports to the boss."""
    scada = app.scada
    capture(scada)
    boss_node = getattr(scada, boss)
    scada.set_command_tree(boss_node)
    root = boss_node.handle.split(".")[0]
    five_v_boss = scada.layout.five_v_boss
    cycler = scada.pico_cycler
    vdc = scada.layout.vdc_relay
    assert five_v_boss.handle == f"{root}.{H0N.five_v_boss}"
    assert cycler.handle == f"{five_v_boss.handle}.{H0N.pico_cycler}"
    assert vdc.handle == f"{cycler.handle}.{vdc.name}"
    others = [n for n in scada.layout.actuators if n.Name != vdc.name]
    assert others
    assert all(n.handle.startswith(f"{boss_node.handle}.") for n in others)


def test_auto_goes_dormant_leaves_pico_cycler_awake(app: ScadaApp) -> None:
    """Admin waking the scada sends GoDormant to leaf-ally and local-control
    only; the pico-cycler runs in every top state."""
    scada = app.scada
    sent = capture(scada)
    scada.auto_trigger(MainAutoEvent.AutoGoesDormant)
    dormant_to = sorted(dst for dst, p in sent if isinstance(p, GoDormant))
    assert dormant_to == sorted([scada.leaf_ally.name, scada.local_control.name])
    assert H0N.pico_cycler not in dormant_to


def test_flatlined_pico_is_cycled_while_admin_holds_tree(app: ScadaApp) -> None:
    """With admin holding the tree, a pico going missing still makes the
    cycler open vdc-relay: the FsmEvent constructs (axiom 2, the cycler is
    the relay's immediate boss) and is addressed to the relay's live handle."""
    scada = app.scada
    capture(scada)
    scada.auto_trigger(MainAutoEvent.AutoGoesDormant)
    cycler = scada.get_communicator(H0N.pico_cycler)
    assert isinstance(cycler, PicoCycler)
    sent = capture(cycler)
    cycler.last_open_time = 0
    actor, hw_uid = next(iter(cycler.pico_by_actor.items()))
    cycler.process_pico_missing(actor, PicoMissing(ActorName=actor.name, PicoHwUid=hw_uid))
    events = [p for dst, p in sent if isinstance(p, FsmEvent)]
    assert len(events) == 1
    event = events[0]
    vdc = scada.layout.vdc_relay
    assert vdc.handle == f"{H0N.admin}.{H0N.five_v_boss}.{H0N.pico_cycler}.{vdc.name}"
    assert event.ToHandle == vdc.handle
    assert event.FromHandle == f"{H0N.admin}.{H0N.five_v_boss}.{H0N.pico_cycler}"
    assert event.EventName == ChangeRelayState.OpenRelay
