"""The LocalControl selection facade: a Nolan-strategy layout selects
NolanLocalControl (layout family first, ops mode second); the top machine
boots into Normal (the scripted witness) and segues to Monitor; on a layout
without the witness's target records the script skips cleanly."""

import pytest

from actors.local_control.nolan import NolanLocalControl
from actors.local_control_loader import LocalControl
from gwsproto.enums import LocalControlTopEvent, LocalControlTopState
from gwsproto.named_types import FsmEvent, SingleMachineState
from scada_app import ScadaApp

LC_NAME = "lc"


@pytest.fixture
def app() -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.is_simulated = True
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


@pytest.fixture
def impl(app: ScadaApp) -> NolanLocalControl:
    lc = LocalControl(LC_NAME, app)
    assert isinstance(lc._impl, NolanLocalControl)
    inner = lc._impl
    inner.sent = []
    inner._send_to = lambda dst, payload, src=None: inner.sent.append(
        (dst.name, payload)
    )
    return inner


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
        "Monitor",
        "Normal",
        "Dormant",
        "Monitor",
    ]
    assert all(
        s.StateEnum == LocalControlTopState.enum_name() for s in states
    )


@pytest.mark.asyncio
async def test_scripted_witness_skips_without_records(
    impl: NolanLocalControl, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pinned fixture has no fancoil circuit and no secondary-pump
    relay: the witness must command nothing and segue to Monitor."""
    monkeypatch.setattr(NolanLocalControl, "STARTUP_DELAY_S", 0.01)
    await impl._scripted_witness()
    assert impl.top_state == LocalControlTopState.Monitor
    commands = [p for _, p in impl.sent if isinstance(p, FsmEvent)]
    assert commands == []
