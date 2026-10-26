"""The scada loads its stored contract when it starts, and once it holds a
forecast tells the LTN and the leaf ally about the one it loaded. An offer
that arrives in the first seconds is not read back from the store: the
leaf ally gets no heartbeat for it, and a contract the ally gave up stays
ended. A live contract in the store is taken up again after a restart; a
contract the store holds as ended is not. A scada that restarts refusing
dispatch ends the live contract it finds in the store."""

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from actors.contract_handler import CONTRACT_FILE_NAME
from actors.leaf_ally_loader import LeafAlly
from actors.scada import Scada
from gwsproto.enums import (
    DispatchRefusalReason,
    LeafAllyAllTanksState,
    LeafAllyBufferOnlyState,
    MainAutoState,
    SiegLoopStrategy,
    SlowDispatchContractStatus,
)
from gwsproto.named_types import SlowContractHeartbeat, SlowDispatchContract
from gwsproto.names.core.node_names import CoreNodeNames
from scada_app import ScadaApp
from sema_to_dc import load_layout
from tests.actors.test_cold_handling import CONFIG, WILLOW, heating_ops
from tests.actors.test_operating_status import ltn_hb
from tests.utils.scada_live_test_helper import ScadaLiveTest, fresh_buffer, ops_word_with
from weather_source import SimWeatherSource

# Longer than the scada's wait before it speaks of the contract it loaded.
PAST_STARTUP_S = 6

NOT_JUDGED = {
    LeafAllyAllTanksState.Dormant,
    LeafAllyAllTanksState.Initializing,
    LeafAllyBufferOnlyState.Dormant,
    LeafAllyBufferOnlyState.Initializing,
}


class Sends:
    """What the scada sends, by destination, recorded and passed on."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, scada: Scada) -> None:
        self.scada = scada
        self.sent: list[tuple[str, Any]] = []
        scada_send = scada._send_to

        def record(to_node, payload, from_node=None):
            self.sent.append((to_node.name, payload))
            scada_send(to_node, payload, from_node)

        monkeypatch.setattr(scada, "_send_to", record)

    def heartbeats_to_ltn(self) -> list[SlowContractHeartbeat]:
        return [
            p for to, p in self.sent
            if to == self.scada.ltn.name and isinstance(p, SlowContractHeartbeat)
        ]

    def to_leaf_ally(self, payload_type: type) -> list[Any]:
        return [
            p for to, p in self.sent
            if to == self.scada.leaf_ally.name and isinstance(p, payload_type)
        ]

    def to_ltn(self, payload_type: type) -> list[Any]:
        return [
            p for to, p in self.sent
            if to == self.scada.ltn.name and isinstance(p, payload_type)
        ]


async def scada_tasks_started(h: ScadaLiveTest) -> None:
    """The scada's own tasks are running, so its stored contract is loaded."""
    await h.await_for(
        lambda: any(t.get_name() == "scada top_state_tracker" for t in asyncio.all_tasks()),
        "ERROR waiting for the scada's tasks to start",
    )


def leaf_ally(scada: Scada) -> LeafAlly:
    ally = scada.services.get_communicator_as_type(CoreNodeNames.leaf_ally, LeafAlly)
    assert ally is not None
    return ally


def live_contract(scada: Scada) -> SlowDispatchContract:
    """A contract on the next five-minute slot, an hour long."""
    return SlowDispatchContract(
        ScadaAlias=scada.layout.scada_g_node_alias,
        StartS=(int(time.time()) // 300) * 300 + 300,
        DurationMinutes=60,
        AvgPowerWatts=1000,
        OilBoilerOn=False,
        ContractId=str(uuid.uuid4()),
    )


def stored_heartbeat(
    scada_alias: str,
    status: SlowDispatchContractStatus = SlowDispatchContractStatus.Active,
) -> SlowContractHeartbeat:
    """The scada's own heartbeat on a contract that started this slot, as
    the store holds it: live by default, or ended as the status says."""
    contract = SlowDispatchContract(
        ScadaAlias=scada_alias,
        StartS=(int(time.time()) // 300) * 300,
        DurationMinutes=60,
        AvgPowerWatts=1000,
        OilBoilerOn=False,
        ContractId=str(uuid.uuid4()),
    )
    ended = status in {
        SlowDispatchContractStatus.TerminatedByScada,
        SlowDispatchContractStatus.CompletedUnknownOutcome,
    }
    return SlowContractHeartbeat(
        FromNode=CoreNodeNames.primary_scada,
        Contract=contract,
        PreviousStatus=(
            SlowDispatchContractStatus.Active if ended else SlowDispatchContractStatus.Confirmed
        ),
        Status=status,
        Cause="Ally Gives up: test" if ended else None,
        Reason=DispatchRefusalReason.ScadaBlind if ended else None,
        WattHoursUsed=120,
        MessageCreatedMs=int(time.time() * 1000),
        MyDigit=4,
        YourLastDigit=5,
    )


def store(app: ScadaApp, hb: SlowContractHeartbeat) -> Path:
    """The heartbeat in the scada's contract store, where its contract
    handler reads it at start."""
    path = Path(app.settings.paths.data_dir) / CONTRACT_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(hb.model_dump_json(by_alias=True, indent=4))
    return path


@pytest.mark.asyncio
async def test_an_offer_in_the_first_seconds_is_not_read_back_from_the_store(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ops_path = heating_ops(tmp_path, WILLOW)
    layout = load_layout(CONFIG / WILLOW[0], ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        h.start_child1()
        await scada_tasks_started(h)
        started_s = time.time()
        scada = h.child1_app.scada
        sends = Sends(monkeypatch, scada)
        contract = live_contract(scada)
        scada.process_scada_message(scada.ltn, ltn_hb(scada, contract, SlowDispatchContractStatus.Created))
        await h.await_for(
            lambda: time.time() > started_s + PAST_STARTUP_S,
            "ERROR waiting out the startup seconds",
            timeout=PAST_STARTUP_S + 5,
        )
        assert sends.to_leaf_ally(SlowContractHeartbeat) == []
        latest = scada.contract_handler.latest_scada_hb
        assert latest is None or (
            latest.Contract.ContractId == contract.ContractId
            and latest.Status == SlowDispatchContractStatus.Received
        )


@pytest.mark.asyncio
async def test_a_live_stored_contract_is_taken_up_again_after_a_restart(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ops_path = heating_ops(tmp_path, WILLOW)
    layout = load_layout(CONFIG / WILLOW[0], ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        app = h.child1_app
        stored = stored_heartbeat(layout.scada_g_node_alias)
        contract = stored.Contract
        store(app, stored)

        h.start_child1()
        scada = app.scada
        fresh_buffer(scada)  # ahead of the resume, which runs seconds after start
        sends = Sends(monkeypatch, scada)
        await h.await_for(
            lambda: scada.auto_state == MainAutoState.LeafTransactiveNode
            and bool(sends.heartbeats_to_ltn()),
            "ERROR waiting for the scada to take the stored contract up again",
            timeout=30,
            err_str_f=lambda: (
                f"auto_state: {scada.auto_state}, "
                f"latest_scada_hb: {scada.contract_handler.latest_scada_hb}"
            ),
        )
        latest = scada.contract_handler.latest_scada_hb
        assert latest is not None
        assert latest.Contract.ContractId == contract.ContractId
        assert scada.contract_handler.energy_used_wh == 120
        assert {hb.Contract.ContractId for hb in sends.heartbeats_to_ltn()} == {contract.ContractId}
        assert contract in sends.to_leaf_ally(SlowDispatchContract)


@pytest.mark.asyncio
async def test_a_resumed_contract_waits_for_the_first_forecast(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The resume runs as its own task and awaits the first forecast. While
    the first fetch is held open the loaded contract is not given up, no
    heartbeat leaves the scada, and an LTN continuation heartbeat for the
    loaded contract is dropped: an Active reply while LocalControl runs
    the house would put the loaded heartbeat out of order at the LTN.
    Opening the pin sends the loaded heartbeat, and the ally judges."""
    ops_path = heating_ops(tmp_path, WILLOW)
    layout = load_layout(CONFIG / WILLOW[0], ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        app = h.child1_app
        weather = app.weather_source
        assert isinstance(weather, SimWeatherSource)
        weather.release.clear()
        stored = stored_heartbeat(layout.scada_g_node_alias)
        contract = stored.Contract
        store(app, stored)

        h.start_child1()
        scada = app.scada
        fresh_buffer(scada)  # ahead of the resume
        sends = Sends(monkeypatch, scada)
        await scada_tasks_started(h)
        started_s = time.time()
        await h.await_for(
            lambda: time.time() > started_s + PAST_STARTUP_S,
            "ERROR waiting out the startup seconds",
            timeout=PAST_STARTUP_S + 5,
        )
        latest = scada.contract_handler.latest_scada_hb
        assert latest is not None, "the resumed contract was given up"
        assert latest.Contract.ContractId == contract.ContractId
        assert sends.heartbeats_to_ltn() == [], "a heartbeat left before the first forecast"
        assert sends.to_leaf_ally(SlowDispatchContract) == []

        scada.process_scada_message(
            scada.ltn, ltn_hb(scada, contract, SlowDispatchContractStatus.Active)
        )
        assert sends.heartbeats_to_ltn() == [], "a continuation heartbeat was answered"

        weather.release.set()
        await h.await_for(
            lambda: bool(sends.heartbeats_to_ltn()),
            "ERROR waiting for the scada to speak of the stored contract",
            timeout=30,
        )
        assert sends.heartbeats_to_ltn()[0] == stored
        assert scada.auto_state == MainAutoState.LeafTransactiveNode
        assert contract in sends.to_leaf_ally(SlowDispatchContract)
        ally = leaf_ally(scada)
        await h.await_for(
            lambda: ally.state not in NOT_JUDGED,
            "ERROR waiting for the ally's first judgment",
            timeout=10,
            err_str_f=lambda: f"ally state: {ally.state}",
        )


def refusing_ops(tmp_path: Path, reason: DispatchRefusalReason) -> Path:
    """Willow's ops word holding dispatch for the reason; the operator's hold
    also puts the house in standby."""
    source = heating_ops(tmp_path, WILLOW)
    dest = tmp_path / "refusing-operational-params.json"
    if reason == DispatchRefusalReason.OperatorHold:
        return ops_word_with(
            source, dest, standby=True, sieg_loop_strategy=SiegLoopStrategy.HoldFullSend
        )
    return ops_word_with(source, dest, service_contract_broken=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason", [DispatchRefusalReason.OperatorHold, DispatchRefusalReason.ServiceContractBroken]
)
async def test_a_live_stored_contract_is_ended_by_a_scada_that_refuses_dispatch(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason: DispatchRefusalReason,
) -> None:
    ops_path = refusing_ops(tmp_path, reason)
    layout = load_layout(CONFIG / WILLOW[0], ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        app = h.child1_app
        stored = stored_heartbeat(layout.scada_g_node_alias)
        contract = stored.Contract
        contract_file = store(app, stored)

        h.start_child1()
        scada = app.scada
        sends = Sends(monkeypatch, scada)
        await h.await_for(
            lambda: bool(sends.heartbeats_to_ltn()),
            "ERROR waiting for the scada to speak of the stored contract",
            timeout=30,
            err_str_f=lambda: (
                f"auto_state: {scada.auto_state}, "
                f"latest_scada_hb: {scada.contract_handler.latest_scada_hb}"
            ),
        )
        [ended] = sends.heartbeats_to_ltn()
        assert ended.Contract.ContractId == contract.ContractId
        assert ended.Status == SlowDispatchContractStatus.TerminatedByScada
        assert ended.WattHoursUsed == 120
        assert ended.Reason == reason
        assert scada.auto_state == MainAutoState.LocalControl
        assert scada.contract_handler.latest_scada_hb is None
        assert sends.to_leaf_ally(SlowDispatchContract) == []
        assert sends.to_leaf_ally(SlowContractHeartbeat) == []
        in_store = SlowContractHeartbeat.model_validate_json(contract_file.read_text())
        assert in_store.Status == SlowDispatchContractStatus.TerminatedByScada


@pytest.mark.asyncio
async def test_a_stored_contract_that_ended_is_not_taken_up_after_a_restart(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ops_path = heating_ops(tmp_path, WILLOW)
    layout = load_layout(CONFIG / WILLOW[0], ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        app = h.child1_app
        store(
            app,
            stored_heartbeat(
                layout.scada_g_node_alias, SlowDispatchContractStatus.TerminatedByScada
            ),
        )

        h.start_child1()
        await scada_tasks_started(h)
        started_s = time.time()
        scada = app.scada
        sends = Sends(monkeypatch, scada)
        assert scada.contract_handler.latest_scada_hb is None
        await h.await_for(
            lambda: time.time() > started_s + PAST_STARTUP_S
            and scada.auto_state == MainAutoState.LocalControl,
            "ERROR waiting out the startup seconds in LocalControl",
            timeout=30,
            err_str_f=lambda: f"auto_state: {scada.auto_state}",
        )
        assert scada.contract_handler.latest_scada_hb is None
        assert scada.auto_state == MainAutoState.LocalControl
        assert sends.heartbeats_to_ltn() == []
        assert sends.to_leaf_ally(SlowDispatchContract) == []


@pytest.mark.asyncio
async def test_an_offer_in_local_control_sends_the_leaf_ally_the_contract_once(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ops_path = heating_ops(tmp_path, WILLOW)
    layout = load_layout(CONFIG / WILLOW[0], ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        h.start_child1()
        await scada_tasks_started(h)
        scada = h.child1_app.scada
        await h.await_for(
            lambda: scada.auto_state == MainAutoState.LocalControl,
            "ERROR waiting for auto to wake into LocalControl",
            timeout=30,
        )
        sends = Sends(monkeypatch, scada)
        fresh_buffer(scada)
        contract = live_contract(scada)
        scada.process_scada_message(scada.ltn, ltn_hb(scada, contract, SlowDispatchContractStatus.Created))
        assert scada.auto_state == MainAutoState.LeafTransactiveNode
        assert sends.to_leaf_ally(SlowDispatchContract) == [contract]
