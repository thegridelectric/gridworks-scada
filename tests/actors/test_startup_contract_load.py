"""The scada loads its stored contract when it starts, and a few seconds
into its run tells the LTN and the leaf ally about the one it loaded. An
offer that arrives in those seconds is not read back from the store: the
leaf ally gets no heartbeat for it, and a contract the ally gave up stays
ended. A live contract in the store is taken up again after a restart; a
contract the store holds as ended is not. A scada that restarts refusing
dispatch ends the live contract it finds in the store."""

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from actors.scada import Scada
from gwsproto.enums import (
    DispatchRefusalReason,
    MainAutoState,
    SiegLoopStrategy,
    SlowDispatchContractStatus,
)
from gwsproto.named_types import SlowContractHeartbeat, SlowDispatchContract
from sema_to_dc import load_layout
from tests.actors.test_cold_handling import CONFIG, WILLOW, heating_ops
from tests.actors.test_operating_status import ltn_hb
from tests.utils.scada_live_test_helper import ScadaLiveTest

# Longer than the scada's wait before it speaks of the contract it loaded.
PAST_STARTUP_S = 6


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


async def scada_tasks_started(h: ScadaLiveTest) -> None:
    """The scada's own tasks are running, so its stored contract is loaded."""
    await h.await_for(
        lambda: any(t.get_name() == "scada top_state_tracker" for t in asyncio.all_tasks()),
        "ERROR waiting for the scada's tasks to start",
    )


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
        contract = SlowDispatchContract(
            ScadaAlias=layout.scada_g_node_alias,
            StartS=(int(time.time()) // 300) * 300,
            DurationMinutes=60,
            AvgPowerWatts=1000,
            OilBoilerOn=False,
            ContractId=str(uuid.uuid4()),
        )
        stored = SlowContractHeartbeat(
            FromNode="s",
            Contract=contract,
            PreviousStatus=SlowDispatchContractStatus.Confirmed,
            Status=SlowDispatchContractStatus.Active,
            WattHoursUsed=120,
            MessageCreatedMs=int(time.time() * 1000),
            MyDigit=4,
            YourLastDigit=5,
        )
        contract_file = Path(app.settings.paths.data_dir) / "slow_dispatch_contract.json"
        contract_file.parent.mkdir(parents=True, exist_ok=True)
        contract_file.write_text(stored.model_dump_json(indent=4))

        h.start_child1()
        scada = app.scada
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


def refusing_ops(tmp_path: Path, reason: DispatchRefusalReason) -> Path:
    """Willow's ops word refusing dispatch for the reason; Standby also
    selects the standby local control."""
    ops_path = heating_ops(tmp_path, WILLOW, AcceptsDispatch=False, DispatchRefusalReason=reason.value)
    if reason == DispatchRefusalReason.Standby:
        ops = json.loads(ops_path.read_text())
        ops["Standby"] = True
        ops["FamilyParams"]["SiegLoopStrategy"] = SiegLoopStrategy.HoldFullSend.value
        ops_path.write_text(json.dumps(ops, indent=2))
    return ops_path


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason", [DispatchRefusalReason.Standby, DispatchRefusalReason.ServiceContractBroken]
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
        contract = SlowDispatchContract(
            ScadaAlias=layout.scada_g_node_alias,
            StartS=(int(time.time()) // 300) * 300,
            DurationMinutes=60,
            AvgPowerWatts=1000,
            OilBoilerOn=False,
            ContractId=str(uuid.uuid4()),
        )
        stored = SlowContractHeartbeat(
            FromNode="s",
            Contract=contract,
            PreviousStatus=SlowDispatchContractStatus.Confirmed,
            Status=SlowDispatchContractStatus.Active,
            WattHoursUsed=120,
            MessageCreatedMs=int(time.time() * 1000),
            MyDigit=4,
            YourLastDigit=5,
        )
        contract_file = Path(app.settings.paths.data_dir) / "slow_dispatch_contract.json"
        contract_file.parent.mkdir(parents=True, exist_ok=True)
        contract_file.write_text(stored.model_dump_json(indent=4))

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
        assert ended.Cause is not None and reason.value in ended.Cause
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
        contract = SlowDispatchContract(
            ScadaAlias=layout.scada_g_node_alias,
            StartS=(int(time.time()) // 300) * 300,
            DurationMinutes=60,
            AvgPowerWatts=1000,
            OilBoilerOn=False,
            ContractId=str(uuid.uuid4()),
        )
        stored = SlowContractHeartbeat(
            FromNode="s",
            Contract=contract,
            PreviousStatus=SlowDispatchContractStatus.Active,
            Status=SlowDispatchContractStatus.TerminatedByScada,
            Cause="Ally Gives up: test",
            WattHoursUsed=120,
            MessageCreatedMs=int(time.time() * 1000),
            MyDigit=4,
            YourLastDigit=5,
        )
        contract_file = Path(app.settings.paths.data_dir) / "slow_dispatch_contract.json"
        contract_file.parent.mkdir(parents=True, exist_ok=True)
        contract_file.write_text(stored.model_dump_json(indent=4))

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
        contract = live_contract(scada)
        scada.process_scada_message(scada.ltn, ltn_hb(scada, contract, SlowDispatchContractStatus.Created))
        assert scada.auto_state == MainAutoState.LeafTransactiveNode
        assert sends.to_leaf_ally(SlowDispatchContract) == [contract]
