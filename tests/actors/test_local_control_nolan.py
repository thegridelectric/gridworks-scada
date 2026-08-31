"""NolanLocalControl: layout-family selection, the top machine, and TOU
cooling — the schedule at its boundaries, the state-command sequencing
(ON: iso valve OpenValve → pump CloseRelay → call CloseRelay; OFF: call →
pump OpenRelay), the zone holds (SwitchToScada + ops OpenRelay on circuit
positions 1/2/4), and the two prevention layers: gw.nolan.layout axiom 3
rejects a plant-incomplete layout at decode, and construction crashes —
never degrades — if the contract is somehow bypassed.

Selection/top-machine tests ride the pinned Nolan fixture; TOU tests ride
the frozen spruce artifact."""

import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest
import pytz

from actors.local_control.nolan import NolanLocalControl
from actors.local_control_loader import LocalControl
from gwsproto.enums import LocalControlTopEvent, LocalControlTopState
from gwsproto.named_types import (
    FsmEvent,
    NolanOperationalParams,
    NolanLayout,
    SingleMachineState,
)
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.node_names import (
    HydronicSpaceheatNodeNames as HSNN,
)
from gwsproto.names.nolan.node_names import NolanNodeNames
from scada_app import ScadaApp
from sema_to_dc import assemble_runtime_layout

LC_NAME = CoreNodeNames.local_control
SPRUCE_LAYOUT = Path(__file__).parent.parent / "config" / "gw.nolan.layout.json"
SPRUCE_OPS = (
    Path(__file__).parent.parent
    / "config"
    / "gw.nolan.operational.params.json"
)
ET = pytz.timezone("America/New_York")


@pytest.fixture
def app() -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


def make_impl(app: ScadaApp) -> NolanLocalControl:
    lc = LocalControl(LC_NAME, app)
    assert isinstance(lc._impl, NolanLocalControl)
    inner = lc._impl
    inner.sent = []
    inner._send_to = lambda dst, payload, src=None: inner.sent.append(
        (dst.name, payload)
    )
    return inner


@pytest.fixture
def impl(app: ScadaApp) -> NolanLocalControl:
    return make_impl(app)


@pytest.fixture
def spruce_impl(tmp_path: Path) -> NolanLocalControl:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = SPRUCE_LAYOUT
    settings.paths.operational_params = SPRUCE_OPS
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return make_impl(scada_app)


def test_nolan_layout_selects_nolan_local_control(impl: NolanLocalControl) -> None:
    assert impl.top_state == LocalControlTopState.Normal


def test_top_machine_round_trip(impl: NolanLocalControl) -> None:
    impl.trigger_top_event(LocalControlTopEvent.MonitorOnly)
    assert impl.top_state == LocalControlTopState.Monitor
    impl.trigger_top_event(LocalControlTopEvent.MonitorAndControl)
    assert impl.top_state == LocalControlTopState.Normal
    impl.trigger_top_event(LocalControlTopEvent.TopGoDormant)
    assert impl.top_state == LocalControlTopState.Dormant
    impl.trigger_top_event(LocalControlTopEvent.TopWakeUp)
    assert impl.top_state == LocalControlTopState.Monitor

    states = [p for _, p in impl.sent if isinstance(p, SingleMachineState)]
    assert [s.State for s in states] == [
        LocalControlTopState.Monitor,
        LocalControlTopState.Normal,
        LocalControlTopState.Dormant,
        LocalControlTopState.Monitor,
    ]
    assert all(s.StateEnum == LocalControlTopState.enum_name() for s in states)


# ---- the schedule at its boundaries ----


def dt(day: int, hour: int, minute: int) -> datetime:
    # 2026-08-10 is a Monday; day is the calendar day in that week
    return ET.localize(datetime(2026, 8, day, hour, minute))


def test_hp_should_be_on_boundaries(impl: NolanLocalControl) -> None:
    on = impl.hp_should_be_on
    assert on(dt(15, 12, 0))  # Saturday, mid-on-peak hours: weekend ON
    assert on(dt(10, 6, 59))  # weekday pre-peak
    assert not on(dt(10, 7, 0))  # on-peak opens
    assert not on(dt(10, 11, 59))
    assert on(dt(10, 12, 0))  # midday shoulder
    assert not on(dt(10, 16, 0))  # evening peak
    assert not on(dt(10, 19, 59))
    assert on(dt(10, 20, 0))  # evening peak closes


# ---- the TOU loop against the spruce plant records ----


def fsm_events(impl: NolanLocalControl) -> list[tuple[str, str]]:
    return [(dst, p.EventName) for dst, p in impl.sent if isinstance(p, FsmEvent)]


def test_resolves_spruce_plant_targets(spruce_impl: NolanLocalControl) -> None:
    assert spruce_impl.layout.iso_valve.name == NolanNodeNames.iso_valve_relay
    assert spruce_impl.layout.secondary_pump_relay.name == NolanNodeNames.secondary_pump_relay
    assert spruce_impl.layout.hp_scada_ops_relay.name == HSNN.hp_scada_ops_relay
    assert sorted(
        c.CircuitPosition for c, _, _ in spruce_impl._held_circuit_relays
    ) == [
        1,
        2,
        4,
    ]


def test_on_and_off_sequencing(
    spruce_impl: NolanLocalControl, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(NolanLocalControl, "SEQUENCE_STEP_S", 0.01)
    asyncio.run(spruce_impl.turn_on_hp())
    on_targets = [dst for dst, _ in fsm_events(spruce_impl)]
    assert on_targets == [
        NolanNodeNames.iso_valve_relay,
        NolanNodeNames.secondary_pump_relay,
        HSNN.hp_scada_ops_relay,
    ]
    spruce_impl.sent.clear()
    asyncio.run(spruce_impl.turn_off_hp())
    off_targets = [dst for dst, _ in fsm_events(spruce_impl)]
    assert off_targets == [
        HSNN.hp_scada_ops_relay,
        NolanNodeNames.secondary_pump_relay,
    ]


def test_zone_holds_command_failsafe_and_release_ops(
    spruce_impl: NolanLocalControl,
) -> None:
    spruce_impl.command_zone_holds()
    targets = [dst for dst, _ in fsm_events(spruce_impl)]
    assert targets == [
        "zone1-bedrooms-failsafe-relay",
        "zone1-bedrooms-ops-relay",
        "zone2-living-rm-failsafe-relay",
        "zone2-living-rm-ops-relay",
        "zone4-garage-failsafe-relay",
        "zone4-garage-ops-relay",
    ]


def test_missing_plant_node_is_a_crash_not_a_degrade(
    app: ScadaApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """gw.nolan.layout axiom 3 forces the plant nodes to exist at decode;
    if construction ever sees one missing anyway (contract bypassed), the
    actor must crash — never run partially blind."""
    monkeypatch.setattr(NolanLocalControl, "REQUIRED_NODES", ("no-such-node",))
    with pytest.raises(ValueError, match="required node no-such-node"):
        LocalControl(LC_NAME, app)


def test_layout_without_plant_nodes_fails_decode() -> None:
    """The prevention itself: a Nolan layout missing a plant relay node is
    INVALID — axiom 3 (RequiredRelays) rejects it at decode, on the
    same static+ops assembly path the boot uses. The counterexample is
    built by typed mutation of a valid decode, re-validated at the
    boundary."""
    config = Path(__file__).parent.parent / "config"
    ops = NolanOperationalParams.model_validate_json(
        (config / "gw.nolan.operational.params.json").read_text()
    )
    layout = NolanLayout.model_validate(
        assemble_runtime_layout(
            json.loads((config / "gw.nolan.layout.json").read_text()),
            ops.model_dump(by_alias=True, exclude_none=True),
        )
    )
    layout.ShNodes = [
        n for n in layout.ShNodes if n.Name != NolanNodeNames.iso_valve_relay
    ]
    with pytest.raises(ValueError, match="Axiom 3 \\(RequiredRelays\\)"):
        NolanLayout.model_validate(layout.model_dump(by_alias=True, exclude_none=True))
