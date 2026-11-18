"""The scada's contract timing runs on the plant clock: the end-of-contract
wait and the grace check follow the clock the app was built with, a
rejection is stamped from it, and a scada on the coordinator's clock loads
its stored contract at the first step, when plant time exists."""

import asyncio
import json
import uuid
from pathlib import Path

import pytest

from actors.contract_handler import CONTRACT_FILE_NAME
from actors.scada import Scada
from clock import Clock, ManualClock, TimestepClock
from gwsproto.enums import DispatchRefusalReason, SlowDispatchContractStatus
from gwsproto.named_types import (
    SlowContractHeartbeat,
    SlowContractRejection,
    SlowDispatchContract,
)
from gwsproto.names.core.node_names import CoreNodeNames
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
LAYOUT = "gw.house0.orange.layout.json"
OPS = "gw.house0.orange.operational.params.json"
START = 1_700_000_000 - 1_700_000_000 % 3600
END = START + 3600


def build(clock: Clock) -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / LAYOUT
    settings.paths.operational_params = CONFIG / OPS
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings, clock=clock)
    app.instantiate()
    return app


def recorded(scada: Scada) -> list[tuple[str, object]]:
    sent: list[tuple[str, object]] = []
    scada._send_to = lambda to_node, payload, from_node=None: sent.append((to_node.name, payload))
    return sent


def contract(scada: Scada) -> SlowDispatchContract:
    return SlowDispatchContract(
        ScadaAlias=scada.layout.scada_g_node_alias,
        StartS=START,
        DurationMinutes=60,
        AvgPowerWatts=1000,
        ContractId=str(uuid.uuid4()),
        DispatchTerms="dispatch.terms.first.isone.hack",
    )


def offer(c: SlowDispatchContract) -> SlowContractHeartbeat:
    return SlowContractHeartbeat(
        FromNode=CoreNodeNames.ltn,
        Contract=c,
        Status=SlowDispatchContractStatus.Created,
        MessageCreatedMs=START * 1000 + 2000,
        MyDigit=3,
    )


def heartbeats_to_ltn(scada: Scada, sent: list[tuple[str, object]]) -> list[SlowContractHeartbeat]:
    return [p for to, p in sent if to == scada.ltn.name and isinstance(p, SlowContractHeartbeat)]


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_the_end_of_contract_wait_runs_on_the_plant_clock() -> None:
    clock = ManualClock(start_s=START + 2)
    scada = build(clock).scada
    sent = recorded(scada)
    scada.contract_handler.start_new_contract_hb(offer(contract(scada)))
    task = asyncio.create_task(scada.handle_contract_timing())
    try:
        clock.advance(END + 119 - clock.now())  # one second short of the warning time
        await settle()
        assert heartbeats_to_ltn(scada, sent) == []
        clock.advance(1)
        await settle()
        completions = heartbeats_to_ltn(scada, sent)
        assert [c.Status for c in completions] == [SlowDispatchContractStatus.CompletedUnknownOutcome]
        assert completions[0].MessageCreatedMs == clock.now_ms()
    finally:
        task.cancel()


def test_the_grace_period_is_judged_on_the_plant_clock() -> None:
    clock = ManualClock(start_s=START + 2)
    scada = build(clock).scada
    recorded(scada)
    scada.contract_handler.start_new_contract_hb(offer(contract(scada)))
    clock.advance(END + 1 - clock.now())
    assert scada.in_grace_period()  # the contract expired on the clock; the grace period runs
    clock.advance(5 * 60)
    assert not scada.in_grace_period()


def test_a_rejection_is_stamped_from_the_plant_clock() -> None:
    clock = ManualClock(start_s=START + 2)
    scada = build(clock).scada
    sent = recorded(scada)
    Path(scada.settings.paths.tadeed).unlink(missing_ok=True)  # no deed on file: dispatch refused
    scada.process_slow_contract_heartbeat(scada.ltn, offer(contract(scada)))
    rejections = [p for _, p in sent if isinstance(p, SlowContractRejection)]
    assert [r.Reason for r in rejections] == [DispatchRefusalReason.NoTaDeed]
    assert rejections[0].MessageCreatedMs == clock.now_ms()


@pytest.mark.asyncio
async def test_a_timestep_scada_loads_its_stored_contract_at_the_first_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ScadaApp.get_settings()
    clock = TimestepClock(config=settings.gridworks_mqtt)
    monkeypatch.setattr(clock, "start", lambda: None)  # no broker in this test
    app = build(clock)
    scada = app.scada
    recorded(scada)
    c = contract(scada)
    stored = SlowContractHeartbeat(
        FromNode=CoreNodeNames.primary_scada,
        Contract=c,
        PreviousStatus=SlowDispatchContractStatus.Confirmed,
        Status=SlowDispatchContractStatus.Active,
        WattHoursUsed=120,
        MessageCreatedMs=START * 1000 + 5000,
        MyDigit=4,
        YourLastDigit=5,
    )
    path = Path(app.settings.paths.data_dir) / CONTRACT_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stored.model_dump_json(by_alias=True, indent=4))

    tasks = scada.start_tasks()
    try:
        await settle()
        assert scada.contract_handler.latest_scada_hb is None  # no plant time yet
        step = {"TypeName": "sim.timestep", "TimeUnixS": START + 1800}
        clock.process_payload(json.dumps(step).encode())
        await asyncio.sleep(0.2)
        loaded = scada.contract_handler.latest_scada_hb
        assert loaded is not None and loaded.Contract.ContractId == c.ContractId
        assert scada.contract_handler.energy_updated_s == START + 1800
    finally:
        for t in [*tasks, scada.resume_task]:
            t.cancel()
