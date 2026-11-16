"""The scada takes the LTN's one amendment of the contract it holds: the
body is replaced under the same ContractId, the energy accounting keeps
running, and a second amendment is ignored, as the contract's terms allow
one."""

import time
import uuid
from pathlib import Path

import pytest

from actors.contract_handler import ContractHandler
from gwsproto.enums import SlowDispatchContractStatus
from gwsproto.named_types import SlowContractHeartbeat, SlowDispatchContract


class Logger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        self.warnings.append(msg)


class Node:
    Name = "s"


def handler(tmp_path: Path) -> ContractHandler:
    h = ContractHandler.__new__(ContractHandler)
    h.node = Node()
    h.logger = Logger()
    h.contract_file = tmp_path / "slow_dispatch_contract.json"
    h.latest_scada_hb = None
    h.prev = None
    h.amendments = 0
    h.latest_power_w = 0
    h.energy_used_wh = 0
    h.energy_updated_s = None
    return h


def contract(**changes) -> SlowDispatchContract:
    now = int(time.time())
    fields = dict(
        ScadaAlias="hw1.isone.me.versant.keene.beech.scada",
        StartS=now - now % 3600,
        DurationMinutes=60,
        AvgPowerWatts=0,
        ContractId=str(uuid.uuid4()),
        DispatchTerms="dispatch.terms.first.isone.hack",
    )
    fields.update(changes)
    return SlowDispatchContract(**fields)


def offer(c: SlowDispatchContract) -> SlowContractHeartbeat:
    return SlowContractHeartbeat(
        FromNode="ltn",
        Contract=c,
        Status=SlowDispatchContractStatus.Created,
        MessageCreatedMs=c.StartS * 1000 + 2000,
        MyDigit=3,
    )


def amendment(c: SlowDispatchContract, watts: int, your_digit: int) -> SlowContractHeartbeat:
    return SlowContractHeartbeat(
        FromNode="ltn",
        Contract=c.model_copy(update={"AvgPowerWatts": watts}),
        PreviousStatus=SlowDispatchContractStatus.Received,
        Status=SlowDispatchContractStatus.Amended,
        Cause="Final price",
        MessageCreatedMs=int(time.time() * 1000),
        MyDigit=5,
        YourLastDigit=your_digit,
    )


def test_the_amendment_replaces_the_body_and_keeps_the_energy_running(tmp_path: Path) -> None:
    h = handler(tmp_path)
    c = contract()
    received = h.start_new_contract_hb(offer(c))
    h.latest_power_w = 3600
    h.energy_updated_s = time.time() - 60  # a minute at 3.6 kW
    reply = h.amend_contract_hb(amendment(c, 4200, received.MyDigit))

    assert reply is not None
    assert reply.Status is SlowDispatchContractStatus.Active
    assert reply.PreviousStatus is SlowDispatchContractStatus.Amended
    assert reply.Contract.ContractId == c.ContractId
    assert reply.Contract.AvgPowerWatts == 4200
    assert reply.WattHoursUsed == pytest.approx(60, abs=2)
    assert h.latest_scada_hb is reply
    assert h.remaining_watthours == pytest.approx(4200 - 60, abs=2)
    assert h.amendments == 1
    stored = SlowContractHeartbeat.model_validate_json(h.contract_file.read_text())
    assert stored.Contract.AvgPowerWatts == 4200


def test_a_second_amendment_is_ignored(tmp_path: Path) -> None:
    h = handler(tmp_path)
    c = contract()
    received = h.start_new_contract_hb(offer(c))
    first = h.amend_contract_hb(amendment(c, 4200, received.MyDigit))
    assert first is not None
    second = h.amend_contract_hb(amendment(c, 1000, first.MyDigit))
    assert second is None
    assert h.latest_scada_hb.Contract.AvgPowerWatts == 4200
    assert any("allows 1" in w for w in h.logger.warnings)


def test_an_amendment_under_unknown_terms_is_ignored(tmp_path: Path) -> None:
    h = handler(tmp_path)
    c = contract(DispatchTerms="dispatch.terms.nobody.knows")
    received = h.start_new_contract_hb(offer(c))
    assert h.amend_contract_hb(amendment(c, 4200, received.MyDigit)) is None
    assert h.latest_scada_hb.Contract.AvgPowerWatts == 0


def test_an_amendment_of_another_contract_raises(tmp_path: Path) -> None:
    h = handler(tmp_path)
    c = contract()
    received = h.start_new_contract_hb(offer(c))
    with pytest.raises(ValueError):
        h.amend_contract_hb(amendment(contract(), 4200, received.MyDigit))


def test_a_new_contract_resets_the_amendment_count(tmp_path: Path) -> None:
    h = handler(tmp_path)
    c = contract()
    received = h.start_new_contract_hb(offer(c))
    h.amend_contract_hb(amendment(c, 4200, received.MyDigit))
    h.latest_scada_hb = h.latest_scada_hb.model_copy(
        update={"Status": SlowDispatchContractStatus.CompletedUnknownOutcome, "Cause": "done"}
    )
    h.flush_latest_scada_hb()
    assert h.amendments == 0
