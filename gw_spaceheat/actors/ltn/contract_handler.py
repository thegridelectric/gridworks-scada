
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
from gwsproto.enums import SlowDispatchContractStatus
from gwsproto.named_types import ( 
    Bid, DispatchTermsFirstIsoneHack, LatestPrice, SlowContractHeartbeat, SlowContractRejection, SlowDispatchContract, 
)
from gwsproto.names.core.node_names import CoreNodeNames

from actors.ltn.config import LtnSettings

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
        send_threadsafe: Callable[[Message], None]
    ):
        self.settings = settings
        self.node = node
        self.layout = layout
        self.logger = logger
        self.send_threadsafe = send_threadsafe
        self._stop_requested = False
        self.timezone = pytz.timezone(self.settings.timezone_str)
        self.contract_file = Path(
            f"{self.settings.paths.data_dir}/slow_dispatch_contract.json"
        )
        self.next_contract_energy_wh: Optional[int] = None
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
        self.hp_is_off: bool = True  # as the LTN last saw the heat pump's relay
        self.provisional_wh: Optional[int] = None  # the bid's reading at the Provisional
        self.final_received: bool = False
        self.amended: bool = False

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
            if time.time() > hb.Contract.contract_end_s():
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
        self.energy_updated_s = time.time()
        self.store_heartbeat(scada_hb)
       
        if scada_hb.Status == SlowDispatchContractStatus.CompletedUnknownOutcome:
            self.latest_hb = None # we can create new contract now!
            if self.can_create_contract():
                self.create_new_contract()
        elif scada_hb.Status == SlowDispatchContractStatus.TerminatedByScada:
            self.latest_hb = None
        else:
            self.latest_hb = scada_hb
    
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

    def create_new_contract(self) -> None:
        """
        - Create a new SlowDispatchContract at the top of the hour
        - Create a new Heartbeat, stores in latest_hb
        - Sends new Heartbeat to Scada
        """
        if self.next_contract_energy_wh is None:
            raise Exception("next_contract_energy_wh should not be None!")
        reading_wh = self.next_contract_energy_wh
        self.next_contract_energy_wh = None

        now = time.time()
        after_top_s =now % 3600
        if after_top_s >= 10:
            self.logger.info(f"Not starting new contract! more than 10 seconds after top of hour: {round(after_top_s)}")
            return
        
        if self.latest_price is None:
            self.logger.info("Don't have a latest price. Not creating new contract")
            return

        if self.latest_hb is not None:
            self.logger.info("WHY IS latest_hb not none??")
            self.latest_hb = None

        # Only create if there's no active contract or the active contract is done
        if self.latest_hb:
            raise Exception("Cannot create new contract while one is active")
            
        # Create contract starting at the top of this hour
        now = time.time()
        start_s = int(now - (now % 3600))

        # The price is Provisional: the offer may take the house toward less
        # consumption, and a turn-on waits for the Final (or the deadline).
        self.provisional_wh = reading_wh
        self.final_received = False
        self.amended = False
        watthours = reading_wh
        if watthours > 0 and self.hp_is_off:
            self.logger.info(
                f"Heat pump off at the Provisional: offering 0 W, {watthours} Wh waits for the Final"
            )
            watthours = 0

        duration_minutes=60
        avg_power_watts = int(watthours * (60/duration_minutes))
        contract = SlowDispatchContract(
            ScadaAlias=self.layout.scada_g_node_alias,
            StartS=start_s,
            DurationMinutes=duration_minutes,
            AvgPowerWatts=avg_power_watts,
            ContractId=str(uuid.uuid4()),
            DispatchTerms=self.dispatch_terms.TypeName,
        )
        
        # Create initial heartbeat
        hb = SlowContractHeartbeat(
            FromNode=self.node.name,
            Contract=contract,
            Status=SlowDispatchContractStatus.Created,
            MessageCreatedMs=int(time.time() * 1000),
            MyDigit=random.choice(range(10)),
            YourLastDigit=None,  # First message in chain
        )
    
        # Update and store the heartbeat
        self.latest_hb = hb
        self.store_heartbeat()
        
        self.logger.info(f"Created new contract! {self.formatted_contract(self.latest_hb)}")
        # Send hb to scada
        self.send_threadsafe(
                Message(
                    Src=self.node.name,
                    Dst=CoreNodeNames.primary_scada,
                    Payload=self.latest_hb,
                )
            )

    def settle_at_final(self, reading_wh: int) -> None:
        """The Final price for the slot of the contract held: amend the
        contract to the bid's reading at it where that differs from the
        offer."""
        self.final_received = True
        self.amend_to(reading_wh, cause=f"Final price: {reading_wh} Wh")

    def final_deadline_passed(self) -> None:
        """FinalDeadlineS after the slot opened with no Final: the
        Provisional is the Final, and the contract is amended to the bid's
        reading at it where the offer held back."""
        if self.final_received or self.provisional_wh is None:
            return
        self.amend_to(
            self.provisional_wh,
            cause=f"No Final within {self.dispatch_terms.FinalDeadlineS} s: the Provisional is the Final",
        )

    def amend_to(self, reading_wh: int, cause: str) -> None:
        """The one amendment of the contract held: a heartbeat with the same
        ContractId, the new body and Status Amended, sent to the scada."""
        if self.latest_hb is None or self.latest_hb.Status in self.DONE_STATES:
            self.logger.info(f"No contract to amend ({cause})")
            return
        held = self.latest_hb.Contract
        avg_power_watts = int(reading_wh * (60 / held.DurationMinutes))
        if avg_power_watts == held.AvgPowerWatts:
            self.logger.info(f"Contract stands at {held.AvgPowerWatts} W ({cause})")
            return
        if self.amended:
            self.logger.warning(
                f"Not amending again to {avg_power_watts} W: {self.dispatch_terms.TypeName} "
                f"allows {self.dispatch_terms.AmendmentsAllowed} ({cause})"
            )
            return
        contract = held.model_copy(update={"AvgPowerWatts": avg_power_watts})
        hb = SlowContractHeartbeat(
            FromNode=self.node.name,
            Contract=contract,
            PreviousStatus=self.latest_hb.Status,
            Status=SlowDispatchContractStatus.Amended,
            Cause=cause,
            MessageCreatedMs=int(time.time() * 1000),
            MyDigit=random.choice(range(10)),
            YourLastDigit=self.latest_hb.MyDigit,
        )
        self.amended = True
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
                # Only send heartbeats if we have an active contract              
                if self.latest_hb and self.latest_hb.Status in self.ACTIVE_STATES:
                        # Check if contract has expired
                        if time.time() > self.latest_hb.Contract.contract_end_s():
                            # Contract expired - initiate completion
                            completion_hb = self.create_completion_heartbeat()
                            self.send_threadsafe(
                                Message(
                                    Src=self.node.name,
                                    Dst=CoreNodeNames.primary_scada,
                                    Payload=completion_hb
                                )
                            )
                        else:
                            if self.latest_hb.Status == SlowDispatchContractStatus.Created: 
                                send_hb = self.latest_hb # RESEND first contract
                            else:
                                send_hb = self.create_midcontract_heartbeat() # Create a mid-contract heartbeat
                
                            self.send_threadsafe(
                                Message(
                                    Src=self.node.name,
                                    Dst=CoreNodeNames.primary_scada,
                                    Payload=send_hb
                                )
                            )
            except Exception as e:
                self.logger.error(f"Error in heartbeat cycle: {e}")
            # Wait for next heartbeat interval
            await asyncio.sleep(self.HEARTBEAT_INTERVAL_S)
    
    def start_completing_old_contract(self) -> None:
        """
        """
        if self.latest_hb is None:
            raise Exception("Only call when latest_hb exists")
        
        if self.latest_hb.Contract.contract_end_s() > time.time():
            raise Exception("Past the top of the hour but still in prev contract timeslot!?")
        
        try:
            self.send_threadsafe(Message(Src=self.node.name, Dst=CoreNodeNames.primary_scada,
                            Payload=self.create_completion_heartbeat())
            )
        except Exception as e:
            self.logger.info(f"Tried to send contract completion in process_latest_price. Perhaps race cond? {e}")

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
            MessageCreatedMs=int(time.time() * 1000),
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
        if not time.time() > self.latest_hb.Contract.contract_end_s():
            raise Exception("Should not call this if contract time is not over!")
        hb = SlowContractHeartbeat(
            FromNode=self.node.name,
            Contract=self.latest_hb.Contract,
            PreviousStatus=self.latest_hb.Status,
            Status=SlowDispatchContractStatus.CompletedUnknownOutcome,
            Cause="Ltn notes MarketSlot complete",
            MessageCreatedMs=int(time.time() * 1000),
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
        if time.time() > self.latest_hb.Contract.contract_end_s():
            raise Exception("Don't call this for an expired contract!")
        if self.latest_hb.Status in (SlowDispatchContractStatus.Created, SlowDispatchContractStatus.Amended):
            return self.latest_hb # haven't gotten the scada's ack yet
        elif self.latest_hb.Status in [SlowDispatchContractStatus.Received, SlowDispatchContractStatus.Confirmed, SlowDispatchContractStatus.Active]:
                return SlowContractHeartbeat(
                    FromNode=self.node.name,
                    Contract=self.latest_hb.Contract,
                    Status=SlowDispatchContractStatus.Active,
                    MessageCreatedMs=int(time.time() * 1000),
                    MyDigit=random.choice(range(10)),
                    YourLastDigit=self.latest_hb.MyDigit, 
                )
        else:
            raise Exception(f"Cannot call this if latest_hb.Status is {self.latest_hb.Status}")

    def can_create_contract(self) -> bool:
        """ layout received, no latest_hb, and have calculated next energy"""
        return self.layout_received \
                and self.latest_hb is None \
                and self.next_contract_energy_wh is not None
        
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

    
    