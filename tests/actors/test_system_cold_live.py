"""House0's SystemCold transition on a running scada: a house cold with
its buffer empty leaves Normal, and the commands that follow depend on
whether the house has an oil boiler."""

from pathlib import Path
from typing import Any

import pytest
from gwproactor import MonitoredName

from actors.local_control.house0.tou_base import LocalControlTouBase
from gwsproto.enums import (
    ChangeAquastatControl,
    ChangeHeatPumpControl,
    ChangeRelayState,
    ChangeStoreFlowRelay,
    LocalControlTopState,
    TurnHpOnOff,
)
from gwsproto.named_types import FsmEvent
from sema_to_dc import load_layout
from tests.actors.test_cold_handling import CONFIG, WILLOW, heating_ops
from tests.actors.test_cold_handling_live import fast_watch, heating_impl, hold_cold
from tests.utils.scada_live_test_helper import ScadaLiveTest


def fast_local_control(monkeypatch: pytest.MonkeyPatch) -> None:
    """A local control that looks every second and calls the system cold
    after two, beside a watch fast enough to record the setpoint the zone
    is judged against."""
    fast_watch(monkeypatch)
    monkeypatch.setattr(LocalControlTouBase, "MAIN_LOOP_SLEEP_SECONDS", 1)
    monkeypatch.setattr(LocalControlTouBase, "SYSTEM_COLD_MINUTES", 2 / 60)
    # The watchdog cannot sample a timeout scaled to a loop this fast.
    monkeypatch.setattr(
        LocalControlTouBase, "monitored_names",
        property(lambda self: [MonitoredName(self.name, 300)]),
    )


async def system_cold_commands(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    oil_boiler_backup: bool,
) -> tuple[LocalControlTouBase, set[tuple[str, str]]]:
    """Run willow until its local control is in Normal, hold it cold with
    the buffer empty, and return the local control with the (node, event)
    commands it sent from its backup node."""
    fast_local_control(monkeypatch)
    ops_path = heating_ops(tmp_path, WILLOW, OilBoilerBackup=oil_boiler_backup)
    layout = load_layout(CONFIG / WILLOW[0], ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        h.start_child1()
        impl = heating_impl(h.child1_app)
        assert isinstance(impl, LocalControlTouBase)
        sent: list[tuple[str, Any]] = []
        impl_send = impl._send_to

        def record(dst, payload, src=None):
            sent.append((dst.name, payload))
            impl_send(dst, payload, src)

        monkeypatch.setattr(impl, "_send_to", record)
        await h.await_for(
            lambda: impl.actuators_ready and impl.top_state == LocalControlTopState.Normal,
            "ERROR waiting for the local control to hold the tree in Normal",
            timeout=30,
            err_str_f=lambda: f"top state: {impl.top_state}, ready: {impl.actuators_ready}",
        )
        held_in_normal = impl.my_actuators()
        monkeypatch.setattr(impl, "is_buffer_empty", lambda *args, **kwargs: True)

        def cold_and_out_of_normal() -> bool:
            hold_cold(impl, "zone1-main", "zone1-main-temp")
            return impl.top_state != LocalControlTopState.Normal

        await h.await_for(
            cold_and_out_of_normal,
            "ERROR waiting for SystemCold",
            timeout=30,
            err_str_f=lambda: f"top state: {impl.top_state}",
        )
        backup = impl.layout.local_control_backup_node
        assert impl.layout.hp_boss.handle == f"{backup.handle}.{impl.layout.hp_boss.name}"
        assert held_in_normal
        assert all(node.handle.startswith(f"{backup.handle}.") for node in held_in_normal)
        assert impl.normal_node_state() == "Dormant"
        commands = {
            (dst, str(payload.EventName))
            for dst, payload in sent
            if isinstance(payload, FsmEvent) and payload.FromHandle == backup.handle
        }
        return impl, commands


@pytest.mark.asyncio
async def test_a_cold_house0_house_with_a_boiler_hands_the_house_to_the_boiler(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    impl, commands = await system_cold_commands(request, tmp_path, monkeypatch, True)
    assert impl.top_state == LocalControlTopState.InBackup
    assert commands == {
        (impl.layout.store_pump_relay.name, ChangeRelayState.OpenRelay.value),
        (impl.layout.store_charge_discharge_relay.name, ChangeStoreFlowRelay.DischargeStore.value),
        (impl.layout.hp_failsafe_relay.name, ChangeHeatPumpControl.SwitchToTankAquastat.value),
        (impl.layout.aquastat_control_relay.name, ChangeAquastatControl.SwitchToBoiler.value),
    }


@pytest.mark.asyncio
async def test_a_cold_house0_house_with_no_boiler_runs_its_heat_pump(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    impl, commands = await system_cold_commands(request, tmp_path, monkeypatch, False)
    assert impl.top_state == LocalControlTopState.InBackup
    assert commands == {
        (impl.layout.store_pump_relay.name, ChangeRelayState.OpenRelay.value),
        (impl.layout.store_charge_discharge_relay.name, ChangeStoreFlowRelay.DischargeStore.value),
        (impl.layout.hp_boss.name, TurnHpOnOff.TurnOn.value),
    }
