"""The shared cold handling on a running scada, on both sim families: the
cold-watch actor's loop makes the watch and the latch reaches the scada.
A Nolan house holding no contract raises the glitch, keeps accepting
dispatch and stays in Normal. A House0 house cold with its stores empty
under a dispatch contract ends it and refuses dispatch in its operational
params file and on its operating status."""

import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from gwproactor import MonitoredName

import actors.hydronic.cold as cold
from actors.hydronic.cold import ColdWatch
from actors.in_process_messages import BreakServiceContract
from actors.local_control.house0.tou_base import LocalControlTouBase
from actors.local_control.nolan.buffer_only_tou import NolanBufferOnlyTou
from actors.local_control_loader import LocalControl
from actors.scada import Scada
from gwsproto.enums import (
    DispatchRefusalReason,
    LocalControlTopState,
    MainAutoState,
    SlowDispatchContractStatus,
)
from gwsproto.named_types import (
    Glitch,
    HouseOperatingStatus,
    OperationalParams,
    SlowContractHeartbeat,
    SlowDispatchContract,
)
from gwsproto.names.core.node_names import CoreNodeNames
from scada_app import ScadaApp
from sema_to_dc import load_layout
from tests.actors.test_cold_handling import CONFIG, NOLAN, WILLOW, calling, heating_ops, put_f
from tests.utils.scada_live_test_helper import ScadaLiveTest

LATCH_S = 2


class Recorder:
    """What the cold watch and the scada send, recorded and passed on."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, scada: Scada, watch: ColdWatch) -> None:
        self.from_watch: list[Any] = []
        self.from_scada: list[Any] = []
        watch_send, scada_send = watch._send_to, scada._send_to

        def record_watch(dst, payload, src=None):
            self.from_watch.append(payload)
            watch_send(dst, payload, src)

        def record_scada(to_node, payload, from_node=None):
            self.from_scada.append(payload)
            scada_send(to_node, payload, from_node)

        monkeypatch.setattr(watch, "_send_to", record_watch)
        monkeypatch.setattr(scada, "_send_to", record_scada)

    def cold_glitches(self) -> list[Glitch]:
        return [
            p for p in self.from_watch
            if isinstance(p, Glitch) and p.Summary == cold.CRITICAL_ZONE_COLD
        ]

    def breaks(self) -> list[BreakServiceContract]:
        return [p for p in self.from_watch if isinstance(p, BreakServiceContract)]

    def refusals(self) -> list[HouseOperatingStatus]:
        return [
            p for p in self.from_scada
            if isinstance(p, HouseOperatingStatus)
            and p.DispatchRefusalReason == DispatchRefusalReason.ServiceContractBroken
        ]


def heating_impl(app: ScadaApp) -> LocalControlTouBase | NolanBufferOnlyTou:
    lc = app.get_communicator_as_type(CoreNodeNames.local_control, LocalControl)
    assert lc is not None
    assert isinstance(lc._impl, (LocalControlTouBase, NolanBufferOnlyTou))
    return lc._impl


def cold_watch(app: ScadaApp) -> ColdWatch:
    watch = app.get_communicator_as_type(CoreNodeNames.cold_watch, ColdWatch)
    assert watch is not None
    return watch


def fast_watch(monkeypatch: pytest.MonkeyPatch) -> None:
    """A two-second latch on a watch that looks every second."""
    monkeypatch.setattr(cold, "COLD_LATCH_S", LATCH_S)
    monkeypatch.setattr(ColdWatch, "WATCH_S", 1)
    # The watchdog cannot sample a timeout scaled to a loop this fast.
    monkeypatch.setattr(
        ColdWatch, "monitored_names",
        property(lambda self: [MonitoredName(self.name, 300)]),
    )


def hold_cold(impl: ColdWatch, zone: str, temp_channel: str) -> None:
    """A learned zone calling for heat, ten degrees under the setpoint its
    channel carries. Written again on every poll, since the sim devices
    keep reporting."""
    put_f(impl, f"{zone}-set", 70)
    put_f(impl, temp_channel, 60)
    calling(impl, zone, True)


def assert_refused(scada: Scada, ops_path: Path, seen: Recorder) -> None:
    assert scada.ops.AcceptsDispatch is False
    assert scada.ops.DispatchRefusalReason == DispatchRefusalReason.ServiceContractBroken
    assert OperationalParams.model_validate_json(ops_path.read_text()) == scada.ops
    assert len(seen.refusals()) == 1
    assert len(seen.cold_glitches()) == 1


@pytest.mark.asyncio
async def test_a_cold_nolan_house_holding_no_contract_raises_the_glitch_and_goes_to_cold_override(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fast_watch(monkeypatch)
    ops_path = heating_ops(tmp_path, NOLAN)
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / NOLAN[0]
    settings.paths.operational_params = ops_path
    async with ScadaLiveTest(request=request, child_app_settings=settings, ops_path=ops_path) as h:
        h.start_child1()
        scada = h.child1_app.scada
        impl = heating_impl(h.child1_app)
        assert isinstance(impl, NolanBufferOnlyTou)
        watch = cold_watch(h.child1_app)
        seen = Recorder(monkeypatch, scada, watch)

        monkeypatch.setattr(watch, "stores_empty", lambda: True)

        def cold_and_glitched() -> bool:
            hold_cold(watch, "zone1-bedrooms", "zone1-bedrooms-gw-temp")
            return bool(seen.cold_glitches()) and bool(seen.breaks())

        await h.await_for(
            cold_and_glitched,
            "ERROR waiting for the cold latch",
            timeout=30,
            err_str_f=lambda: f"watch sent: {[type(p).__name__ for p in seen.from_watch]}",
        )
        assert len(seen.cold_glitches()) == 1
        assert seen.refusals() == []
        assert scada.ops.AcceptsDispatch is True
        await h.await_for(
            lambda: impl.top_state == LocalControlTopState.ColdOverride,
            "ERROR waiting for the local control to react to the watch",
            timeout=10,
            err_str_f=lambda: f"top state: {impl.top_state}",
        )
        cold_override = impl.layout.local_control_cold_override_node
        assert impl.layout.hp_boss.handle == f"{cold_override.handle}.{impl.layout.hp_boss.name}"


def ltn_hb(scada: Scada, contract: SlowDispatchContract, status: SlowDispatchContractStatus) -> SlowContractHeartbeat:
    return SlowContractHeartbeat(
        FromNode=scada.ltn.name,
        Contract=contract,
        Status=status,
        MessageCreatedMs=int(time.time() * 1000),
        MyDigit=5,
        YourLastDigit=None,
    )


@pytest.mark.asyncio
async def test_a_house0_house_cold_with_its_stores_empty_under_a_dispatch_contract_ends_it(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fast_watch(monkeypatch)
    ops_path = heating_ops(tmp_path, WILLOW)
    layout = load_layout(CONFIG / WILLOW[0], ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        h.start_child1()
        scada = h.child1_app.scada
        impl = heating_impl(h.child1_app)
        assert isinstance(impl, LocalControlTouBase)
        watch = cold_watch(h.child1_app)
        seen = Recorder(monkeypatch, scada, watch)
        await h.await_for(
            lambda: scada.auto_state == MainAutoState.LocalControl,
            "ERROR waiting for auto to wake into LocalControl",
            timeout=30,
            err_str_f=lambda: f"auto_state: {scada.auto_state}",
        )

        contract = SlowDispatchContract(
            ScadaAlias=scada.layout.scada_g_node_alias,
            StartS=(int(time.time()) // 300) * 300 + 300,
            DurationMinutes=60,
            AvgPowerWatts=1000,
            OilBoilerOn=False,
            ContractId=str(uuid.uuid4()),
        )
        scada.process_scada_message(scada.ltn, ltn_hb(scada, contract, SlowDispatchContractStatus.Created))
        await h.await_for(
            lambda: scada.auto_state == MainAutoState.LeafTransactiveNode
            and impl.top_state == LocalControlTopState.Dormant,
            "ERROR waiting for the leaf ally to take the tree",
            err_str_f=lambda: f"auto_state: {scada.auto_state}, lc: {impl.top_state}",
        )
        assert scada.contract_handler.latest_scada_hb is not None
        monkeypatch.setattr(watch, "stores_empty", lambda: True)

        def cold_and_back_in_local_control() -> bool:
            hold_cold(watch, "zone1-main", "zone1-main-temp")
            return bool(seen.refusals()) and scada.auto_state == MainAutoState.LocalControl

        await h.await_for(
            cold_and_back_in_local_control,
            "ERROR waiting for the cold latch to end the contract",
            timeout=30,
            err_str_f=lambda: (
                f"watch sent: {[type(p).__name__ for p in seen.from_watch]}, "
                f"auto_state: {scada.auto_state}"
            ),
        )
        assert_refused(scada, ops_path, seen)
        assert scada.contract_handler.latest_scada_hb is None

        def cold_state_taken() -> bool:
            hold_cold(watch, "zone1-main", "zone1-main-temp")
            return impl.top_state in (LocalControlTopState.InBackup, LocalControlTopState.ColdOverride)

        await h.await_for(
            cold_state_taken,
            "ERROR waiting for the woken local control to take its cold state",
            timeout=10,
            err_str_f=lambda: f"top state: {impl.top_state}",
        )
        terminations = [
            p for p in seen.from_scada
            if isinstance(p, SlowContractHeartbeat)
            and p.Status == SlowDispatchContractStatus.TerminatedByScada
        ]
        assert [t.Contract.ContractId for t in terminations] == [contract.ContractId]
        assert terminations[0].Cause is not None
        assert terminations[0].Cause.startswith(DispatchRefusalReason.ServiceContractBroken.value)
