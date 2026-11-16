
import asyncio
import json
import random
import time
from datetime import datetime, timedelta
import uuid
from pathlib import Path
from typing import Optional, Callable

import pytz
from gwproto import Message
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwproactor.logger import LoggerOrAdapter
from gwsproto.enums import PriceStage, SlowDispatchContractStatus
from gwsproto.named_types import ( 
    Bid, DispatchTermsFirstIsoneHack, LatestPrice, SlowContractHeartbeat, SlowContractRejection, SlowDispatchContract, 
)
from gwsproto.names.core.node_names import CoreNodeNames

from actors.ltn.config import LtnSettings
from actors.ltn.desired_offer import DesiredOffer

class LtnContractHandler:
    """Handles Ltn's side of representation contract with SCADA and dispatch contracts"""
    HEARTBEAT_INTERVAL_S = 60
    DONE_STATES = [
        SlowDispatchContractStatus.TerminatedByLtn,
        SlowDispatchContractStatus.TerminatedByScada,
        SlowDispatchContractStatus.CompletedUnknownOutcome,
        SlowDispatchContractStatus.CompletedSuccess,
        SlowDispatchContractStatus.CompletedFailureByLtn,
        SlowDispatchContractStatus.CompletedFailureByScada,
    ]
    ACTIVE_STATES = [
        SlowDispatchContractStatus.Created,
        SlowDispatchContractStatus.Received,
        SlowDispatchContractStatus.Confirmed,
        SlowDispatchContractStatus.Active,
        SlowDispatchContractStatus.Amended,
    ]
    HEARTBEAT_INTERVAL_SECONDS = 60  # Send heartbeats once per minute
    LOGGER_NAME = "LtnContractHandler" 
    def __init__(
        self,
        node: ShNode,
        settings: LtnSettings,
        layout: HydronicLayout,
        logger: LoggerOrAdapter,
        send_threadsafe: Callable[[Message], None],
        now: Callable[[], float] = time.time,
    ):
        self.settings = settings
        self.now = now  # the plant clock: one clock for every contract time
        self.node = node
        self.layout = layout
        self.logger = logger
        self.send_threadsafe = send_threadsafe
        self._stop_requested = False
        self.timezone = pytz.timezone(self.settings.timezone_str)
        self.contract_file = Path(
            f"{self.settings.paths.data_dir}/slow_dispatch_contract.json"
        )
        self.desired_offer_file = Path(
            f"{self.settings.paths.data_dir}/desired_offer.json"
        )
        self.energy_used_wh: float = 0
        self.latest_power_w: int = 0
        self.energy_updated_s: Optional[float] = None
        self.layout_received: bool = False # have we received the layout
        self.latest_hb: Optional[SlowContractHeartbeat] = None # Current active hb, None means no active contract
        self.latest_price: Optional[LatestPrice] = None
        self.latest_bid: Optional[Bid] = None
        # The terms every contract is offered under. The market's terms in
        # force are the MarketMaker's to state (market.terms); until the LTN
        # reads that word, these are the one agreement it knows.
        self.dispatch_terms = DispatchTermsFirstIsoneHack()
        # The heat pump as the LTN last saw its relay. Off until a Report
        # says otherwise: under ReduceOnly a wrong "off" holds an offer back
        # to the Final, a wrong "on" turns the heat pump on.
        self.hp_is_off: bool = True
        # What the LTN wants the slot's contract to say; None between slots.
        self.desired: Optional[DesiredOffer] = self.load_desired_offer()

    def load_heartbeat(self) -> Optional[SlowContractHeartbeat]:
        """Loads existing SlowContractHeartbeat from persistent storage
        
        - Returns None if no heartbeat exists
        - Otherwise loads the heartbeat and sets internal state
        """
        if not self.contract_file.exists():
            self.logger.info("No contract file found")
            return None
            
        with open(self.contract_file, "r") as f:
            contract_data = json.load(f)

        try:
            hb = SlowContractHeartbeat.model_validate(contract_data)
            
            # Store as latest heartbeat
            if hb.Status in self.DONE_STATES:
                # This is a completed contract, not active
                self.logger.info("Loaded completed contract")
                return None
        
            # If contract has ended, mark as complete and send that message. Set latest_hb to None
            if self.now() > hb.Contract.contract_end_s():
                if hb.Status not in self.DONE_STATES:
                    # Contract has expired, need to mark as completed
                    self.logger.info("Loaded contract has expired, will send completion heartbeat")
                    completion_hb = self.create_completion_heartbeat()
                    self.latest_hb = None
                    return completion_hb
                else:
                    return None
            else:
                self.logger.info(f"Loaded active contract: {self.formatted_contract(hb)}")
                self.energy_updated_s = hb.MessageCreatedMs / 1000
                if hb.FromNode == self.node.name:
                    if hb.Status not in (SlowDispatchContractStatus.Created, SlowDispatchContractStatus.Amended):
                        raise Exception("Only save ltn heartbeats with status Created or Amended!")
                    self.energy_used_wh = 0
                    self.latest_hb = hb
                    return hb
                else:
                    if hb.WattHoursUsed is None:
                        raise Exception("hb from Scada must have WattHoursUsed!")
                    self.energy_used_wh = hb.WattHoursUsed
                self.latest_hb = hb
                return None
        except Exception as e:
            self.logger.error(
                "Ignoring persisted contract heartbeat due to load error",
                exc_info=e,
            )
            return None
            
    def store_heartbeat(self, hb: Optional[SlowContractHeartbeat] = None) -> None:
        """Stores a SlowContractHeartbeat to persistent storage"""
        hb_to_store = self.latest_hb
        if hb:
            hb_to_store = hb
        if not hb_to_store: 
            raise Exception("Can't store hb if latest_hb is none!")
        
        if hb_to_store.FromNode == self.node.name:
            if hb_to_store.Status not in [SlowDispatchContractStatus.Created,
                                   SlowDispatchContractStatus.Amended,
                                   SlowDispatchContractStatus.TerminatedByLtn,
                                   SlowDispatchContractStatus.CompletedUnknownOutcome]:
                raise Exception(f"Does not store ltn hb with status {hb_to_store.Status}")
        
        with open(self.contract_file, "w") as f:
            f.write(hb_to_store.model_dump_json(indent=4))
    
    def load_desired_offer(self) -> Optional[DesiredOffer]:
        """The desired offer persisted for the slot, or None."""
        if not self.desired_offer_file.exists():
            return None
        try:
            return DesiredOffer.model_validate_json(self.desired_offer_file.read_text())
        except Exception as e:
            self.logger.error("Ignoring persisted desired offer due to load error", exc_info=e)
            return None

    def store_desired_offer(self) -> None:
        if self.desired is None:
            self.desired_offer_file.unlink(missing_ok=True)
        else:
            self.desired_offer_file.write_text(self.desired.model_dump_json(indent=4))

    def initialize(self) -> Optional[SlowContractHeartbeat]:
        """Initialize contract handler state from persistent storage
        
        Returns a heartbeat if one needs to be sent to SCADA
        """
        hb = self.load_heartbeat()        
        return hb

    def process_slow_contract_heartbeat(self, scada_hb: SlowContractHeartbeat) -> None:
        """ - Does nothing if scada_hb does not match (latest_hb is None, mis-match in ContractId,
        or MessageCreatedMs is out of order)
        Otherwise:
          - sets self.latest_hb to this hb
          - updates energy_used_wh and energy_updated_s
          - stores the heartbeat
          - sets latest_hb to None if scada sends Completed or Terminated
          
        """
        if self.latest_hb is None:
            self.logger.info(f"Unexpected Scada hb ... we have no heartbeat! {scada_hb}")
            return
        if scada_hb.Contract.ContractId != self.latest_hb.Contract.ContractId:
            self.logger.info("Not the same ContractId ... ignoring")
            return
        if self.latest_hb is not None:
            if scada_hb.MessageCreatedMs < self.latest_hb.MessageCreatedMs:
                self.logger.info("hb received out of order. Ignoring!")
                return
        if scada_hb.WattHoursUsed is None: 
            raise Exception("this can't happen, axiomatically in Hb")

        self.logger.info(self.formatted_contract(scada_hb))
        self.energy_used_wh = scada_hb.WattHoursUsed
        self.energy_updated_s = self.now()
        self.store_heartbeat(scada_hb)
       
        if scada_hb.Status in (
            SlowDispatchContractStatus.CompletedUnknownOutcome,
            SlowDispatchContractStatus.TerminatedByScada,
        ):
            self.latest_hb = None
        else:
            self.latest_hb = scada_hb
        self.reconcile(self.now())
    
    def process_slow_contract_rejection(self, rejection: SlowContractRejection) -> None:
        """The scada will not take the offered contract. Drop the pending
        Created heartbeat so the rejected offer is not resent or reloaded."""
        if self.latest_hb is None or rejection.ContractId != self.latest_hb.Contract.ContractId:
            self.logger.info(f"Rejection for a contract we are not offering ... ignoring: {rejection}")
            return
        self.logger.warning(
            f"Scada refused contract {rejection.ContractId}: {rejection.Reason.value}"
        )
        self.latest_hb = None
        self.contract_file.unlink(missing_ok=True)

    def slot_start_s(self, now_s: float) -> int:
        return int(now_s - now_s % 3600)

    def set_provisional(self, reading_wh: int, now_s: float) -> None:
        """The maker's Provisional for the slot `now_s` falls in. The desired
        offer takes the house toward less consumption only: the reading when
        the heat pump runs or the reading is zero, else 0 W, and the reading
        is kept for the slot to take if no Final comes."""
        offer_wh = reading_wh
        if offer_wh > 0 and self.hp_is_off:
            self.logger.info(
                f"Heat pump off at the Provisional: offering 0 W, {reading_wh} Wh waits for the Final"
            )
            offer_wh = 0
        self.desired = DesiredOffer(
            SlotStartS=self.slot_start_s(now_s),
            OfferWh=offer_wh,
            Stage=PriceStage.Provisional,
            ProvisionalReadingWh=reading_wh,
        )
        self.store_desired_offer()
        self.reconcile(now_s)

    def set_final(self, reading_wh: int, now_s: float) -> None:
        """The maker's Final for the slot `now_s` falls in: the desired offer
        is the reading, whatever the heat pump is doing."""
        if self.desired is None or self.desired.SlotStartS != self.slot_start_s(now_s):
            self.logger.info("Final for a slot with no Provisional offer: nothing to settle")
            return
        self.desired = self.desired.model_copy(
            update={"OfferWh": reading_wh, "Stage": PriceStage.Final}
        )
        self.store_desired_offer()
        self.reconcile(now_s)

    def reconcile(self, now_s: float) -> None:
        """One step toward the desired offer, from what the scada has said:
        complete an expired held contract; offer the slot's contract when
        none is held and the slot is within 10 s of its start; promote the
        Provisional to Final at the deadline; amend an acked contract whose
        body differs from the desired offer, once. Runs on every price,
        every scada heartbeat and every tick."""
        if self.latest_hb is not None and now_s > self.latest_hb.Contract.contract_end_s():
            if self.latest_hb.Status in self.ACTIVE_STATES:
                self.send_threadsafe(Message(
                    Src=self.node.name, Dst=CoreNodeNames.primary_scada,
                    Payload=self.create_completion_heartbeat(),
                ))
            self.latest_hb = None
        if self.desired is None:
            return
        slot_start_s = self.desired.SlotStartS
        if slot_start_s != self.slot_start_s(now_s):
            self.logger.info("Desired offer is for another slot; dropping it")
            self.desired = None
            self.store_desired_offer()
            return
        if self.latest_hb is None:
            if now_s - slot_start_s <= 10:
                if self.layout_received and self.latest_price is not None:
                    self.create_new_contract(slot_start_s, now_s)
            return
        if self.latest_hb.Contract.StartS != slot_start_s:
            return
        if (
            self.desired.Stage is PriceStage.Provisional
            and now_s >= slot_start_s + self.dispatch_terms.FinalDeadlineS
        ):
            self.logger.info(
                f"No Final within {self.dispatch_terms.FinalDeadlineS} s: the Provisional is the Final"
            )
            self.desired = self.desired.model_copy(update={
                "OfferWh": self.desired.ProvisionalReadingWh,
                "Stage": PriceStage.Final,
                "NoFinal": True,
            })
            self.store_desired_offer()
        if self.latest_hb.Status in (SlowDispatchContractStatus.Created, SlowDispatchContractStatus.Amended):
            return  # unacked; the tick resends it
        self.amend_if_needed(now_s)

    def create_new_contract(self, slot_start_s: int, now_s: float) -> None:
        """Offer the slot's contract at the desired offer: a Created
        heartbeat, stored and sent to the scada."""
        assert self.desired is not None
        if self.latest_hb is not None:
            raise Exception("Cannot create new contract while one is held")
        duration_minutes = 60
        avg_power_watts = int(self.desired.OfferWh * (60 / duration_minutes))
        contract = SlowDispatchContract(
            ScadaAlias=self.layout.scada_g_node_alias,
            StartS=slot_start_s,
            DurationMinutes=duration_minutes,
            AvgPowerWatts=avg_power_watts,
            ContractId=str(uuid.uuid4()),
            DispatchTerms=self.dispatch_terms.TypeName,
        )
        hb = SlowContractHeartbeat(
            FromNode=self.node.name,
            Contract=contract,
            Status=SlowDispatchContractStatus.Created,
            MessageCreatedMs=int(now_s * 1000),
            MyDigit=random.choice(range(10)),
            YourLastDigit=None,  # First message in chain
        )
        self.latest_hb = hb
        self.store_heartbeat()
        self.logger.info(f"Created new contract! {self.formatted_contract(self.latest_hb)}")
        self.send_threadsafe(
            Message(Src=self.node.name, Dst=CoreNodeNames.primary_scada, Payload=self.latest_hb)
        )

    def amend_if_needed(self, now_s: float) -> None:
        """The one amendment of the acked contract held, when its body
        differs from the desired offer: a heartbeat with the same
        ContractId, the new body and Status Amended, stored and sent."""
        assert self.desired is not None and self.latest_hb is not None
        held = self.latest_hb.Contract
        avg_power_watts = int(self.desired.OfferWh * (60 / held.DurationMinutes))
        if avg_power_watts == held.AvgPowerWatts:
            return
        if self.desired.AmendedToWh is not None:
            if self.desired.AmendedToWh != self.desired.OfferWh:
                self.logger.warning(
                    f"Not amending again to {avg_power_watts} W: {self.dispatch_terms.TypeName} "
                    f"allows {self.dispatch_terms.AmendmentsAllowed}"
                )
            return
        if self.desired.NoFinal:
            cause = (
                f"No Final within {self.dispatch_terms.FinalDeadlineS} s: "
                f"the Provisional is the Final, {self.desired.OfferWh} Wh"
            )
        else:
            cause = f"Final price: {self.desired.OfferWh} Wh"
        contract = held.model_copy(update={"AvgPowerWatts": avg_power_watts})
        hb = SlowContractHeartbeat(
            FromNode=self.node.name,
            Contract=contract,
            PreviousStatus=self.latest_hb.Status,
            Status=SlowDispatchContractStatus.Amended,
            Cause=cause,
            MessageCreatedMs=int(now_s * 1000),
            MyDigit=random.choice(range(10)),
            YourLastDigit=self.latest_hb.MyDigit,
        )
        self.desired = self.desired.model_copy(update={"AmendedToWh": self.desired.OfferWh})
        self.store_desired_offer()
        self.latest_hb = hb
        self.store_heartbeat()
        self.logger.info(f"Amended contract! {self.formatted_contract(hb)}")
        self.send_threadsafe(
            Message(Src=self.node.name, Dst=CoreNodeNames.primary_scada, Payload=hb)
        )

    def is_onpeak(self) -> bool:
        time_now = datetime.now(self.timezone)
        time_in_2min = time_now + timedelta(minutes=2)
        peak_hours = [7,8,9,10,11] + [16,17,18,19]
        if (time_now.hour in peak_hours or time_in_2min.hour in peak_hours) and time_now.weekday() < 5:
            return True
        else:
            return False

    async def contract_heartbeat_task(self):
        """Task that sends regular heartbeats while a contract is active"""
        await asyncio.sleep(2)
        hb = self.initialize()
        if hb is not None:
            if hb.Status == SlowDispatchContractStatus.Created:
                # we didn't get any response, send again
                self.send_threadsafe(Message(Src=self.node.name,Dst=CoreNodeNames.primary_scada,Payload=hb))
        while not self._stop_requested:
            try:
                self.reconcile(self.now())
                if self.latest_hb and self.latest_hb.Status in self.ACTIVE_STATES:
                    # Created and Amended resend unchanged until acked
                    self.send_threadsafe(
                        Message(
                            Src=self.node.name,
                            Dst=CoreNodeNames.primary_scada,
                            Payload=self.create_midcontract_heartbeat(),
                        )
                    )
            except Exception as e:
                self.logger.error(f"Error in heartbeat cycle: {e}")
            # Wait for next heartbeat interval
            await asyncio.sleep(self.HEARTBEAT_INTERVAL_S)
    
    def create_termination_heartbeat(self, reason: str) -> SlowContractHeartbeat:
        """Create a heartbeat terminating the current contract"""
        if not self.latest_hb:
            raise Exception("No active contract to terminate")
            
        hb = SlowContractHeartbeat(
            FromNode=self.node.name,
            Contract=self.latest_hb.Contract,
            PreviousStatus=self.latest_hb.Status,
            Status=SlowDispatchContractStatus.TerminatedByLtn,
            Cause=reason,
            MessageCreatedMs=int(self.now() * 1000),
            MyDigit=random.choice(range(10)),
            YourLastDigit=self.latest_hb.MyDigit
        )
        
        # Store heartbeat
        self.store_heartbeat(hb)
        # Clear active contract
        self.latest_hb = None
        return hb
    
    def create_completion_heartbeat(self) -> SlowContractHeartbeat:
        """Create a heartbeat marking the current contract as completed
        """
        if not self.latest_hb:
            raise Exception("No active contract to terminate")
        if not self.now() > self.latest_hb.Contract.contract_end_s():
            raise Exception("Should not call this if contract time is not over!")
        hb = SlowContractHeartbeat(
            FromNode=self.node.name,
            Contract=self.latest_hb.Contract,
            PreviousStatus=self.latest_hb.Status,
            Status=SlowDispatchContractStatus.CompletedUnknownOutcome,
            Cause="Ltn notes MarketSlot complete",
            MessageCreatedMs=int(self.now() * 1000),
            MyDigit=random.choice(range(10)),
            YourLastDigit=self.latest_hb.MyDigit,
        )
        return hb
    
    def create_midcontract_heartbeat(self) -> SlowContractHeartbeat:
        """Generate the next heartbeat in the contract sequence
        
        Will raise an exception if latest_hb is None, if the time is past
        the latest_hb contract end, or if the status is Terminated
        """
        if self.latest_hb is None:
            raise Exception("Should not call this if latest_hb is None!")
        if self.now() > self.latest_hb.Contract.contract_end_s():
            raise Exception("Don't call this for an expired contract!")
        if self.latest_hb.Status in (SlowDispatchContractStatus.Created, SlowDispatchContractStatus.Amended):
            return self.latest_hb # haven't gotten the scada's ack yet
        elif self.latest_hb.Status in [SlowDispatchContractStatus.Received, SlowDispatchContractStatus.Confirmed, SlowDispatchContractStatus.Active]:
                return SlowContractHeartbeat(
                    FromNode=self.node.name,
                    Contract=self.latest_hb.Contract,
                    Status=SlowDispatchContractStatus.Active,
                    MessageCreatedMs=int(self.now() * 1000),
                    MyDigit=random.choice(range(10)),
                    YourLastDigit=self.latest_hb.MyDigit, 
                )
        else:
            raise Exception(f"Cannot call this if latest_hb.Status is {self.latest_hb.Status}")

    def formatted_contract(self, hb_to_format: Optional[SlowContractHeartbeat] = None) -> str:
        """Format contract heartbeat information for logging in a human-readable format."""
        hb = self.latest_hb
        if hb_to_format:
            hb = hb_to_format
        
        if not hb:
            return ""
        
        slot_start = datetime.fromtimestamp(
            hb.Contract.StartS, 
            tz=self.timezone
        ).strftime('%H:%M')

        slot_end = datetime.fromtimestamp(
            hb.Contract.contract_end_s(), 
            tz=self.timezone
        ).strftime('%H:%M')

        created_time = datetime.fromtimestamp(
            hb.MessageCreatedMs / 1000, 
            tz=self.timezone
        ).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        # Calculate total energy for the contract in Wh
        total_energy = hb.Contract.AvgPowerWatts * hb.Contract.DurationMinutes / 60
        
        # Energy used so far (only present in SCADA heartbeats)
        if hb.Status == SlowDispatchContractStatus.Created:
            energy_used = 0
        else:
            energy_used = hb.WattHoursUsed
        
        # Format the log string
        log_str = (
            f"Contract[{hb.Contract.ContractId[:3]}] "
            f"{slot_start} - {slot_end}: "
            f"Total: {total_energy:.1f} Wh | "
            f"Used: {energy_used} Wh | "
            f"Status: {hb.Status.value}  (created by {hb.FromNode} at {created_time})"
        )
        
        # Add reason if present
        if hb.Cause:
            log_str += f" | Reason: {hb.Cause}"
        
        return log_str

    
    