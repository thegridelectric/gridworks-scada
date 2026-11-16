"""The LTN reconciles a desired offer against the contract the scada holds.
The Provisional sets the desired offer toward less consumption only (the
bid's reading when the heat pump runs or the reading is zero, else 0 W),
the Final replaces it, and the deadline promotes a Provisional to Final.
One reconcile step, on every price, scada heartbeat and tick, sends the
one message the difference calls for: completion, Created, Amended once.
Both records persist, so a restart resumes the slot."""

import random
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytz
from gwproto import Message

from actors.ltn.contract_handler import LtnContractHandler
from actors.ltn.desired_offer import DesiredOffer
from gwsproto.enums import PriceStage, SlowDispatchContractStatus
from gwsproto.named_types import DispatchTermsFirstIsoneHack, SlowContractHeartbeat

TOP = 1795060800  # a top of the hour
DEADLINE = DispatchTermsFirstIsoneHack().FinalDeadlineS


class Logger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def info(self, *a, **k) -> None: ...

    def error(self, *a, **k) -> None: ...

    def warning(self, msg, *a, **k) -> None:
        self.warnings.append(msg)


class Node:
    name = "ltn"


class Layout:
    scada_g_node_alias = "hw1.isone.me.versant.keene.beech.scada"


class Price:
    PriceX1000 = 60_000


def handler(tmp_path: Path, hp_is_off: bool) -> tuple[LtnContractHandler, list[Message]]:
    sent: list[Message] = []
    h = LtnContractHandler.__new__(LtnContractHandler)
    h.node = Node()
    h.layout = Layout()
    h.logger = Logger()
    h.timezone = pytz.utc
    h.send_threadsafe = sent.append
    h.contract_file = tmp_path / "slow_dispatch_contract.json"
    h.desired_offer_file = tmp_path / "desired_offer.json"
    h.latest_hb = None
    h.latest_price = Price()
    h.layout_received = True
    h.hp_is_off = hp_is_off
    h.dispatch_terms = DispatchTermsFirstIsoneHack()
    h.desired = h.load_desired_offer()
    h.clock = [TOP + 2]
    h.now = lambda: h.clock[0]
    return h, sent


def reload(h: LtnContractHandler, sent: list[Message]) -> LtnContractHandler:
    """A restart: a fresh handler over the same files."""
    r, _ = handler(h.contract_file.parent, hp_is_off=h.hp_is_off)
    r.send_threadsafe = sent.append
    r.latest_hb = SlowContractHeartbeat.model_validate_json(h.contract_file.read_text())
    return r


def provisional(h: LtnContractHandler, sent: list[Message], reading_wh: int, now_s: float = TOP + 2) -> SlowContractHeartbeat:
    h.set_provisional(reading_wh, at(h, at(h, now_s)))
    hb = sent[-1].Payload
    assert hb.Status is SlowDispatchContractStatus.Created
    assert hb.Contract.DispatchTerms == "dispatch.terms.first.isone.hack"
    return hb


def at(h: LtnContractHandler, now_s: float) -> float:
    h.clock[0] = now_s
    return now_s


def scada_acks(h: LtnContractHandler, status: SlowDispatchContractStatus, now_s: float, watt_hours: int = 0) -> SlowContractHeartbeat:
    """The scada's heartbeat for the contract the LTN last sent."""
    assert h.latest_hb is not None
    at(h, now_s)
    hb = SlowContractHeartbeat(
        FromNode="s",
        Contract=h.latest_hb.Contract,
        PreviousStatus=h.latest_hb.Status,
        Status=status,
        WattHoursUsed=watt_hours,
        MessageCreatedMs=int(now_s * 1000),
        MyDigit=random.choice(range(10)),
        YourLastDigit=h.latest_hb.MyDigit,
    )
    h.process_slow_contract_heartbeat(hb)
    return hb


def statuses(sent: list[Message]) -> list[SlowDispatchContractStatus]:
    return [m.Payload.Status for m in sent]


def amendments(sent: list[Message]) -> list[SlowContractHeartbeat]:
    return [m.Payload for m in sent if m.Payload.Status is SlowDispatchContractStatus.Amended]


# The ReduceOnly rule at the Provisional


def test_a_running_heat_pump_is_offered_the_provisional_reading(tmp_path) -> None:
    h, sent = handler(tmp_path, hp_is_off=False)
    assert provisional(h, sent, 4200).Contract.AvgPowerWatts == 4200
    assert h.desired == DesiredOffer(SlotStartS=TOP, OfferWh=4200, Stage=PriceStage.Provisional, ProvisionalReadingWh=4200)


def test_a_heat_pump_that_is_off_stays_off_until_the_final(tmp_path) -> None:
    h, sent = handler(tmp_path, hp_is_off=True)
    assert provisional(h, sent, 4200).Contract.AvgPowerWatts == 0
    assert h.desired is not None and h.desired.ProvisionalReadingWh == 4200


@pytest.mark.parametrize("hp_is_off", [True, False])
def test_a_zero_reading_is_offered_as_zero(tmp_path, hp_is_off: bool) -> None:
    h, sent = handler(tmp_path, hp_is_off=hp_is_off)
    assert provisional(h, sent, 0).Contract.AvgPowerWatts == 0


def test_a_provisional_before_any_report_counts_the_heat_pump_off(tmp_path) -> None:
    """Difference 9: the stated start is off, the ReduceOnly-safe guess, so
    the first Provisional holds a reading back rather than turn the heat
    pump on."""
    settings = SimpleNamespace(paths=SimpleNamespace(data_dir=str(tmp_path)), timezone_str="UTC")
    h = LtnContractHandler(node=Node(), settings=settings, layout=Layout(), logger=Logger(), send_threadsafe=lambda m: None)
    assert h.hp_is_off is True
    h.clock = [TOP + 2]
    h.now = lambda: h.clock[0]
    sent: list[Message] = []
    h.send_threadsafe = sent.append
    h.latest_price = Price()
    h.layout_received = True
    assert provisional(h, sent, 4200).Contract.AvgPowerWatts == 0


# The Final and the one amendment


def test_the_final_amends_an_acked_held_back_offer_once(tmp_path) -> None:
    h, sent = handler(tmp_path, hp_is_off=True)
    created = provisional(h, sent, 4200)
    scada_acks(h, SlowDispatchContractStatus.Received, TOP + 3)
    h.set_final(3600, at(h, TOP + 30))
    [amended] = amendments(sent)
    assert amended.Contract.ContractId == created.Contract.ContractId
    assert amended.Contract.AvgPowerWatts == 3600
    assert amended.PreviousStatus is SlowDispatchContractStatus.Received
    assert amended.Cause and "Final" in amended.Cause
    assert h.latest_hb is amended
    assert SlowContractHeartbeat.model_validate_json(h.contract_file.read_text()).Status is SlowDispatchContractStatus.Amended


def test_a_final_before_the_ack_amends_after_the_ack(tmp_path) -> None:
    """Difference 3: the amendment waits for the scada's ack."""
    h, sent = handler(tmp_path, hp_is_off=True)
    provisional(h, sent, 4200)
    h.set_final(4200, at(h, TOP + 30))
    assert amendments(sent) == []
    scada_acks(h, SlowDispatchContractStatus.Received, TOP + 31)
    [amended] = amendments(sent)
    assert amended.Contract.AvgPowerWatts == 4200


def test_the_final_turns_a_running_heat_pump_off(tmp_path) -> None:
    h, sent = handler(tmp_path, hp_is_off=False)
    provisional(h, sent, 4200)
    scada_acks(h, SlowDispatchContractStatus.Active, TOP + 3)
    h.set_final(0, at(h, TOP + 30))
    [amended] = amendments(sent)
    assert amended.Contract.AvgPowerWatts == 0


def test_a_final_that_agrees_with_the_offer_amends_nothing(tmp_path) -> None:
    h, sent = handler(tmp_path, hp_is_off=False)
    provisional(h, sent, 4200)
    scada_acks(h, SlowDispatchContractStatus.Active, TOP + 3)
    h.set_final(4200, at(h, TOP + 30))
    assert amendments(sent) == []


def test_only_one_amendment_is_made(tmp_path) -> None:
    h, sent = handler(tmp_path, hp_is_off=True)
    provisional(h, sent, 4200)
    scada_acks(h, SlowDispatchContractStatus.Active, TOP + 3)
    h.set_final(3600, at(h, TOP + 30))
    scada_acks(h, SlowDispatchContractStatus.Active, TOP + 31)
    h.set_final(1000, at(h, TOP + 40))
    assert [a.Contract.AvgPowerWatts for a in amendments(sent)] == [3600]
    assert any("allows 1" in w for w in h.logger.warnings)


def test_a_final_for_another_slot_amends_nothing(tmp_path) -> None:
    """Difference 7: the price's slot is checked against the held contract's."""
    h, sent = handler(tmp_path, hp_is_off=True)
    provisional(h, sent, 4200)
    scada_acks(h, SlowDispatchContractStatus.Active, TOP + 3)
    h.set_final(3600, at(h, TOP + 3600 + 30))
    assert amendments(sent) == []


# The deadline


def test_no_final_by_the_deadline_makes_the_provisional_final(tmp_path) -> None:
    """Difference 5: a plant-clock time checked by the reconcile step."""
    h, sent = handler(tmp_path, hp_is_off=True)
    provisional(h, sent, 4200)
    scada_acks(h, SlowDispatchContractStatus.Active, TOP + 3)
    h.reconcile(at(h, TOP + DEADLINE - 1))
    assert amendments(sent) == []
    h.reconcile(at(h, TOP + DEADLINE))
    [amended] = amendments(sent)
    assert amended.Contract.AvgPowerWatts == 4200
    assert amended.Cause and "Provisional is the Final" in amended.Cause
    assert h.desired is not None and h.desired.Stage is PriceStage.Final


def test_the_deadline_after_a_final_does_nothing(tmp_path) -> None:
    h, sent = handler(tmp_path, hp_is_off=True)
    provisional(h, sent, 4200)
    scada_acks(h, SlowDispatchContractStatus.Active, TOP + 3)
    h.set_final(4200, at(h, TOP + 30))
    scada_acks(h, SlowDispatchContractStatus.Active, TOP + 31)
    h.reconcile(at(h, TOP + DEADLINE))
    assert len(amendments(sent)) == 1


def test_the_deadline_with_nothing_held_back_does_nothing(tmp_path) -> None:
    h, sent = handler(tmp_path, hp_is_off=False)
    provisional(h, sent, 4200)
    scada_acks(h, SlowDispatchContractStatus.Active, TOP + 3)
    h.reconcile(at(h, TOP + DEADLINE))
    assert amendments(sent) == []


def test_an_unreadable_final_leaves_the_deadline_to_promote_the_provisional(tmp_path) -> None:
    """Difference 4: the Ltn does not call set_final for a Final it cannot
    read, so the desired offer stands and the deadline promotes it."""
    h, sent = handler(tmp_path, hp_is_off=True)
    provisional(h, sent, 4200)
    scada_acks(h, SlowDispatchContractStatus.Active, TOP + 3)
    h.reconcile(at(h, TOP + DEADLINE))
    [amended] = amendments(sent)
    assert amended.Contract.AvgPowerWatts == 4200
    assert amended.Cause and "No Final" in amended.Cause


def test_the_deadline_with_no_desired_offer_does_nothing(tmp_path) -> None:
    h, sent = handler(tmp_path, hp_is_off=True)
    h.reconcile(at(h, TOP + DEADLINE))
    assert sent == []


# The slot's Created and the previous slot's completion


def test_a_provisional_completes_the_previous_contract_and_offers_the_new_in_one_step(tmp_path) -> None:
    """Difference 2: the Created does not wait on the completion reply, and
    the reply does not create a second contract."""
    h, sent = handler(tmp_path, hp_is_off=False)
    old = provisional(h, sent, 4200, now_s=TOP - 3600 + 2)
    scada_acks(h, SlowDispatchContractStatus.Active, TOP - 3600 + 3)
    h.set_provisional(3000, at(h, TOP + 2))
    assert statuses(sent)[-2:] == [SlowDispatchContractStatus.CompletedUnknownOutcome, SlowDispatchContractStatus.Created]
    completion, created = sent[-2].Payload, sent[-1].Payload
    assert completion.Contract.ContractId == old.Contract.ContractId
    assert created.Contract.StartS == TOP and created.Contract.AvgPowerWatts == 3000
    # the old contract's completion reply is for another ContractId: ignored
    h.process_slow_contract_heartbeat(SlowContractHeartbeat(
        FromNode="s", Contract=old.Contract, PreviousStatus=SlowDispatchContractStatus.CompletedUnknownOutcome,
        Status=SlowDispatchContractStatus.CompletedUnknownOutcome, Cause="Final energy accounting",
        WattHoursUsed=4100, MessageCreatedMs=(TOP + 3) * 1000, MyDigit=1, YourLastDigit=completion.MyDigit,
    ))
    assert [m.Payload.Contract.StartS for m in sent if m.Payload.Status is SlowDispatchContractStatus.Created].count(TOP) == 1
    assert h.latest_hb is created


def test_an_offer_more_than_ten_seconds_after_the_hour_is_not_made(tmp_path) -> None:
    """Difference 10: a Created is stamped within 10 s of StartS."""
    h, sent = handler(tmp_path, hp_is_off=False)
    h.set_provisional(4200, at(h, TOP + 11))
    assert sent == []
    assert h.desired is not None  # the slot's desired offer stands; a Final finds no contract
    h.set_final(4200, at(h, TOP + 30))
    assert sent == []


def test_a_lost_completion_reply_is_retried_on_the_next_tick(tmp_path) -> None:
    """Difference 8: an expired held contract is completed on every step."""
    h, sent = handler(tmp_path, hp_is_off=False)
    provisional(h, sent, 4200)
    scada_acks(h, SlowDispatchContractStatus.Active, TOP + 3)
    h.reconcile(at(h, TOP + 3601))
    assert statuses(sent)[-1] is SlowDispatchContractStatus.CompletedUnknownOutcome
    assert h.latest_hb is None


# Resends


def test_an_unacked_amendment_is_resent_unchanged_and_the_ack_stops_it(tmp_path) -> None:
    """Difference 6."""
    h, sent = handler(tmp_path, hp_is_off=True)
    provisional(h, sent, 4200)
    scada_acks(h, SlowDispatchContractStatus.Active, TOP + 3)
    h.set_final(3600, at(h, TOP + 30))
    [amended] = amendments(sent)
    h.reconcile(at(h, TOP + 60))
    assert h.create_midcontract_heartbeat() is amended
    h.reconcile(at(h, TOP + 120))
    assert h.create_midcontract_heartbeat() is amended
    scada_acks(h, SlowDispatchContractStatus.Active, TOP + 121)
    assert h.latest_hb is not None and h.latest_hb.Status is SlowDispatchContractStatus.Active
    assert h.create_midcontract_heartbeat().Status is SlowDispatchContractStatus.Active
    assert len(amendments(sent)) == 1


def test_a_received_contract_sends_an_active_heartbeat_on_the_tick(tmp_path) -> None:
    h, sent = handler(tmp_path, hp_is_off=False)
    provisional(h, sent, 4200)
    scada_acks(h, SlowDispatchContractStatus.Received, TOP + 3)
    assert h.create_midcontract_heartbeat().Status is SlowDispatchContractStatus.Active


# Restarts


def test_a_restart_between_the_stages_resumes_the_slot(tmp_path) -> None:
    """Difference 1: both records persist."""
    h, sent = handler(tmp_path, hp_is_off=True)
    provisional(h, sent, 4200)
    scada_acks(h, SlowDispatchContractStatus.Active, TOP + 3)
    r = reload(h, sent)
    assert r.desired == h.desired
    r.set_final(3600, at(r, TOP + 30))
    [amended] = amendments(sent)
    assert amended.Contract.AvgPowerWatts == 3600


def test_a_restart_after_the_amendment_makes_no_second_one(tmp_path) -> None:
    h, sent = handler(tmp_path, hp_is_off=True)
    provisional(h, sent, 4200)
    scada_acks(h, SlowDispatchContractStatus.Active, TOP + 3)
    h.set_final(3600, at(h, TOP + 30))
    scada_acks(h, SlowDispatchContractStatus.Active, TOP + 31)
    r = reload(h, sent)
    r.set_final(1000, at(r, TOP + 40))
    r.reconcile(at(r, TOP + DEADLINE))
    assert [a.Contract.AvgPowerWatts for a in amendments(sent)] == [3600]


def test_a_desired_offer_for_a_past_slot_is_dropped_at_reload(tmp_path) -> None:
    h, sent = handler(tmp_path, hp_is_off=True)
    provisional(h, sent, 4200)
    r = reload(h, sent)
    r.reconcile(at(r, TOP + 3600 + 5))
    assert r.desired is None and not r.desired_offer_file.exists()
