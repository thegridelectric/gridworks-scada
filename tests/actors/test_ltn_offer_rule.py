"""The LTN's rule for the hour's contract across the maker's two price
stages. At the Provisional the offer may take the house toward less
consumption only: the bid's reading when the heat pump is running or the
reading is zero, else 0 W. The Final settles the contract by one amendment
where its reading differs from the offer; with no Final by FinalDeadlineS
the Provisional is the Final and the offer that held back is amended to
its reading."""

import time
from pathlib import Path

import pytest
import pytz
from gwproto import Message

from actors.ltn.contract_handler import LtnContractHandler
from gwsproto.enums import SlowDispatchContractStatus
from gwsproto.named_types import SlowContractHeartbeat

TOP = 1795060800  # a top of the hour


class Logger:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def info(self, msg: str) -> None:
        self.lines.append(msg)

    warning = info
    error = info


class Node:
    name = "ltn"


class Layout:
    scada_g_node_alias = "hw1.isone.me.versant.keene.beech.scada"


class Settings:
    pass


class Price:
    PriceUnit = None

    def __init__(self, usd_per_mwh: float) -> None:
        from gwsproto.enums import MarketPriceUnit

        self.PriceUnit = MarketPriceUnit.USDPerMWh
        self.PriceX1000 = int(usd_per_mwh * 1000)


def handler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hp_is_off: bool, now_s: float = TOP + 2) -> tuple[LtnContractHandler, list[Message]]:
    sent: list[Message] = []
    h = LtnContractHandler.__new__(LtnContractHandler)
    h.node = Node()
    h.layout = Layout()
    h.settings = Settings()
    h.logger = Logger()
    h.timezone = pytz.utc
    h.send_threadsafe = sent.append
    h.contract_file = tmp_path / "slow_dispatch_contract.json"
    h.latest_hb = None
    h.latest_price = Price(60.0)
    h.hp_is_off = hp_is_off
    h.provisional_wh = None
    h.final_received = False
    h.amended = False
    from gwsproto.named_types import DispatchTermsFirstIsoneHack

    h.dispatch_terms = DispatchTermsFirstIsoneHack()
    h.next_contract_energy_wh = None
    monkeypatch.setattr(LtnContractHandler, "is_onpeak", lambda self: True)
    monkeypatch.setattr(time, "time", lambda: now_s)
    return h, sent


def offer(h: LtnContractHandler, sent: list[Message], reading_wh: int) -> SlowContractHeartbeat:
    h.next_contract_energy_wh = reading_wh
    h.create_new_contract()
    hb = sent[-1].Payload
    assert hb.Status is SlowDispatchContractStatus.Created
    assert hb.Contract.DispatchTerms == "dispatch.terms.first.isone.hack"
    return hb


def amendments(sent: list[Message]) -> list[SlowContractHeartbeat]:
    return [m.Payload for m in sent if m.Payload.Status is SlowDispatchContractStatus.Amended]


def test_a_running_heat_pump_is_offered_the_provisional_reading(tmp_path, monkeypatch) -> None:
    h, sent = handler(tmp_path, monkeypatch, hp_is_off=False)
    hb = offer(h, sent, 4200)
    assert hb.Contract.AvgPowerWatts == 4200
    assert h.provisional_wh == 4200


def test_a_heat_pump_that_is_off_stays_off_until_the_final(tmp_path, monkeypatch) -> None:
    h, sent = handler(tmp_path, monkeypatch, hp_is_off=True)
    hb = offer(h, sent, 4200)
    assert hb.Contract.AvgPowerWatts == 0
    assert h.provisional_wh == 4200


@pytest.mark.parametrize("hp_is_off", [True, False])
def test_a_zero_reading_is_offered_as_zero(tmp_path, monkeypatch, hp_is_off: bool) -> None:
    h, sent = handler(tmp_path, monkeypatch, hp_is_off=hp_is_off)
    assert offer(h, sent, 0).Contract.AvgPowerWatts == 0


def test_the_final_amends_the_held_back_offer_once(tmp_path, monkeypatch) -> None:
    h, sent = handler(tmp_path, monkeypatch, hp_is_off=True)
    created = offer(h, sent, 4200)
    h.settle_at_final(3600)
    [amended] = amendments(sent)
    assert amended.Contract.ContractId == created.Contract.ContractId
    assert amended.Contract.AvgPowerWatts == 3600
    assert amended.PreviousStatus is SlowDispatchContractStatus.Created
    assert amended.Cause and "Final" in amended.Cause
    assert h.latest_hb is amended
    assert SlowContractHeartbeat.model_validate_json(h.contract_file.read_text()).Status is SlowDispatchContractStatus.Amended


def test_the_final_turns_a_running_heat_pump_off(tmp_path, monkeypatch) -> None:
    h, sent = handler(tmp_path, monkeypatch, hp_is_off=False)
    offer(h, sent, 4200)
    h.settle_at_final(0)
    [amended] = amendments(sent)
    assert amended.Contract.AvgPowerWatts == 0


def test_a_final_that_agrees_with_the_offer_amends_nothing(tmp_path, monkeypatch) -> None:
    h, sent = handler(tmp_path, monkeypatch, hp_is_off=False)
    offer(h, sent, 4200)
    h.settle_at_final(4200)
    assert amendments(sent) == []


def test_only_one_amendment_is_made(tmp_path, monkeypatch) -> None:
    h, sent = handler(tmp_path, monkeypatch, hp_is_off=True)
    offer(h, sent, 4200)
    h.settle_at_final(3600)
    h.settle_at_final(1000)
    assert [a.Contract.AvgPowerWatts for a in amendments(sent)] == [3600]


def test_no_final_by_the_deadline_makes_the_provisional_final(tmp_path, monkeypatch) -> None:
    h, sent = handler(tmp_path, monkeypatch, hp_is_off=True)
    offer(h, sent, 4200)
    h.final_deadline_passed()
    [amended] = amendments(sent)
    assert amended.Contract.AvgPowerWatts == 4200
    assert amended.Cause and "Provisional is the Final" in amended.Cause


def test_the_deadline_after_a_final_does_nothing(tmp_path, monkeypatch) -> None:
    h, sent = handler(tmp_path, monkeypatch, hp_is_off=True)
    offer(h, sent, 4200)
    h.settle_at_final(4200)
    h.final_deadline_passed()
    assert len(amendments(sent)) == 1


def test_the_deadline_with_nothing_held_back_does_nothing(tmp_path, monkeypatch) -> None:
    h, sent = handler(tmp_path, monkeypatch, hp_is_off=False)
    offer(h, sent, 4200)
    h.final_deadline_passed()
    assert amendments(sent) == []


def test_an_offer_more_than_ten_seconds_after_the_hour_is_not_made(tmp_path, monkeypatch) -> None:
    h, sent = handler(tmp_path, monkeypatch, hp_is_off=False, now_s=TOP + 11)
    h.next_contract_energy_wh = 4200
    h.create_new_contract()
    assert sent == []
