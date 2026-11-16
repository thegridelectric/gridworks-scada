"""The scada's contract times come from the plant clock: a contract expires,
its energy accrues and its heartbeats are stamped by the clock the app was
built with, so a simulated plant runs contracts in simulated time."""

import datetime
import uuid
from pathlib import Path
from types import SimpleNamespace

from actors.contract_handler import ContractHandler
from clock import ManualClock
from gwsproto.enums import SlowDispatchContractStatus
from gwsproto.named_types import SlowContractHeartbeat, SlowDispatchContract

START = 1_700_000_000 - 1_700_000_000 % 3600


class Logger:
    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        pass

    def error(self, msg: str, exc_info=None) -> None:
        raise AssertionError(msg) from exc_info


class Node:
    Name = "s"
    name = "s"


def handler(tmp_path: Path, clock: ManualClock) -> ContractHandler:
    return ContractHandler(
        settings=SimpleNamespace(paths=SimpleNamespace(data_dir=str(tmp_path))),
        layout=None,
        node=Node(),
        timezone=datetime.timezone.utc,
        logger=Logger(),
        clock=clock,
    )


def contract(start_s: int = START) -> SlowDispatchContract:
    return SlowDispatchContract(
        ScadaAlias="hw1.isone.me.versant.keene.beech.scada",
        StartS=start_s,
        DurationMinutes=60,
        AvgPowerWatts=3600,
        ContractId=str(uuid.uuid4()),
        DispatchTerms="dispatch.terms.first.isone.hack",
    )


def offer(c: SlowDispatchContract) -> SlowContractHeartbeat:
    return SlowContractHeartbeat(
        FromNode="ltn",
        Contract=c,
        Status=SlowDispatchContractStatus.Created,
        MessageCreatedMs=c.StartS * 1000 + 2000,
        MyDigit=3,
    )


def test_a_contract_expires_on_the_plant_clock(tmp_path: Path) -> None:
    clock = ManualClock(start_s=START + 2)
    h = handler(tmp_path, clock)
    received = h.start_new_contract_hb(offer(contract()))
    assert received.MessageCreatedMs == clock.now_ms()
    assert not h.active_contract_has_expired()
    clock.advance(3600)
    assert h.active_contract_has_expired()
    completion = h.scada_contract_completion_hb("end reached")
    assert completion.Status == SlowDispatchContractStatus.CompletedUnknownOutcome
    assert completion.MessageCreatedMs == clock.now_ms()


def test_energy_accrues_by_plant_time(tmp_path: Path) -> None:
    clock = ManualClock(start_s=START + 2)
    h = handler(tmp_path, clock)
    h.start_new_contract_hb(offer(contract()))
    h.latest_power_w = 3600
    clock.advance(600)
    h.update_energy_usage(3600)
    assert round(h.energy_used_wh) == 600


def test_a_stored_contract_is_judged_by_the_plant_clock(tmp_path: Path) -> None:
    clock = ManualClock(start_s=START + 2)
    h = handler(tmp_path, clock)
    h.start_new_contract_hb(offer(contract()))
    h.latest_scada_hb = None  # the store keeps it; this handler forgets it

    live = handler(tmp_path, ManualClock(start_s=START + 1800))
    assert live.load_heartbeat() is not None
    assert live.latest_scada_hb is not None
    assert live.energy_updated_s == START + 1800

    ended = handler(tmp_path, ManualClock(start_s=START + 3601))
    expired = ended.load_heartbeat()
    assert ended.latest_scada_hb is None
    assert expired is not None
    assert expired.Status == SlowDispatchContractStatus.CompletedUnknownOutcome
    assert expired.MessageCreatedMs == (START + 3601) * 1000
