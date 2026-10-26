"""House0's SystemCold transition on a running scada: a house cold with
its buffer empty leaves Normal for InBackup or ColdOverride by whether it
goes to its backup when cold, and each state commands from its own node
and holds through the peak."""

import asyncio
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
from gwsproto.names.core.node_names import CoreNodeNames
from sema_to_dc import load_layout
from tests.actors.test_cold_handling import CONFIG, WILLOW, heating_ops, put_f
from tests.actors.test_cold_handling_live import cold_watch, fast_watch, heating_impl, hold_cold
from tests.utils.scada_live_test_helper import ScadaLiveTest


def fast_local_control(monkeypatch: pytest.MonkeyPatch) -> None:
    """A local control that looks every second, beside a watch with a
    two-second latch."""
    fast_watch(monkeypatch)
    monkeypatch.setattr(LocalControlTouBase, "MAIN_LOOP_SLEEP_SECONDS", 1)
    # The watchdog cannot sample a timeout scaled to a loop this fast.
    monkeypatch.setattr(
        LocalControlTouBase, "monitored_names",
        property(lambda self: [MonitoredName(self.name, 300)]),
    )


async def system_cold_commands(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    uses_backup_when_cold: bool,
    cold_state: LocalControlTopState,
    state_node_name: str,
) -> tuple[LocalControlTouBase, set[tuple[str, str]]]:
    """Run willow until its local control is in Normal, hold it cold at
    the watch with the stores empty until the local control is in
    cold_state, and return the (node, event) commands it sent from that
    state's node. The state then holds while it is on-peak and returns to
    Normal off-peak once the watch says the house is warm."""
    fast_local_control(monkeypatch)
    ops_path = heating_ops(tmp_path, WILLOW, UsesBackupWhenCold=uses_backup_when_cold)
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
        watch = cold_watch(h.child1_app)
        monkeypatch.setattr(watch, "stores_empty", lambda: True)

        def cold_and_out_of_normal() -> bool:
            hold_cold(watch, "zone1-main", "zone1-main-temp")
            return impl.top_state != LocalControlTopState.Normal

        await h.await_for(
            cold_and_out_of_normal,
            "ERROR waiting for SystemCold",
            timeout=30,
            err_str_f=lambda: f"top state: {impl.top_state}",
        )
        assert impl.top_state == cold_state
        state_node = impl.layout.node(state_node_name)
        assert state_node is not None
        assert impl.layout.hp_boss.handle == f"{state_node.handle}.{impl.layout.hp_boss.name}"
        assert held_in_normal
        assert all(node.handle.startswith(f"{state_node.handle}.") for node in held_in_normal)
        assert impl.normal_node_state() == "Dormant"
        commands = {
            (dst, str(payload.EventName))
            for dst, payload in sent
            if isinstance(payload, FsmEvent) and payload.FromHandle == state_node.handle
        }

        monkeypatch.setattr(impl, "is_onpeak", lambda: True)
        put_f(watch, "zone1-main-temp", 70)
        await h.await_for(
            lambda: not impl.house_cold,
            "ERROR waiting for the watch to say the house is warm",
            timeout=30,
        )
        await asyncio.sleep(3 * impl.MAIN_LOOP_SLEEP_SECONDS)
        assert impl.top_state == cold_state
        monkeypatch.setattr(impl, "is_onpeak", lambda: False)
        await h.await_for(
            lambda: impl.top_state == LocalControlTopState.Normal,
            "ERROR waiting for the warm off-peak house to return to Normal",
            timeout=30,
            err_str_f=lambda: f"top state: {impl.top_state}",
        )
        normal = impl.layout.local_control_normal_node
        assert impl.layout.hp_boss.handle == f"{normal.handle}.{impl.layout.hp_boss.name}"
        return impl, commands


@pytest.mark.asyncio
async def test_a_cold_house0_house_with_a_boiler_hands_the_house_to_the_boiler(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    impl, commands = await system_cold_commands(
        request, tmp_path, monkeypatch, True,
        LocalControlTopState.InBackup, CoreNodeNames.local_control_backup,
    )
    assert commands == {
        (impl.layout.store_pump_relay.name, ChangeRelayState.OpenRelay.value),
        (impl.layout.store_charge_discharge_relay.name, ChangeStoreFlowRelay.DischargeStore.value),
        (impl.layout.hp_failsafe_relay.name, ChangeHeatPumpControl.SwitchToTankAquastat.value),
        (impl.layout.aquastat_control_relay.name, ChangeAquastatControl.SwitchToBoiler.value),
    }


@pytest.mark.asyncio
async def test_a_cold_house0_house_that_does_not_use_its_backup_runs_its_heat_pump(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    impl, commands = await system_cold_commands(
        request, tmp_path, monkeypatch, False,
        LocalControlTopState.ColdOverride, CoreNodeNames.local_control_cold_override,
    )
    assert commands == {
        (impl.layout.store_pump_relay.name, ChangeRelayState.OpenRelay.value),
        (impl.layout.store_charge_discharge_relay.name, ChangeStoreFlowRelay.DischargeStore.value),
        (impl.layout.hp_boss.name, TurnHpOnOff.TurnOn.value),
    }
