
import asyncio
import json
import random
import time
import datetime
import uuid
from pathlib import Path
from typing import Optional, Callable

import pytz
from gwproto import Message
from gwproto.data_classes.sh_node import ShNode
from data_classes.house_0_layout import House0Layout
from data_classes.house_0_names import H0N
from gwproactor.logger import LoggerOrAdapter
from enums import MarketPriceUnit
from enums import ContractStatus
from named_types import ( 
    AtnBid, LatestPrice, SlowContractHeartbeat, SlowDispatchContract, 
)

from tests.atn.atn_config import AtnSettings

class AtnContractHandler:
    """Handles ATN's side of representation contract with SCADA and dispatch contracts"""
    HEARTBEAT_INTERVAL_S = 60
    DONE_STATES = [
        ContractStatus.TerminatedByAtn,
        ContractStatus.TerminatedByScada,
        ContractStatus.CompletedUnknownOutcome,
        ContractStatus.CompletedSuccess,
        ContractStatus.CompletedFailureByAtn,
        ContractStatus.CompletedFailureByScada,
    ]
    ACTIVE_STATES = [
        ContractStatus.Created,
        ContractStatus.Received,
        ContractStatus.Confirmed,
        ContractStatus.Active
    ]
    HEARTBEAT_INTERVAL_SECONDS = 60  # Send heartbeats once per minute
    LOGGER_NAME = "AtnContractHandler" 
    def __init__(
        self,
        node: ShNode,
        settings: AtnSettings,
        layout: House0Layout,
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
        self.latest_bid: Optional[AtnBid] = None

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
                    if hb.Status != ContractStatus.Created:
                        raise Exception("Only save atn heartbeats with status Created!")
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
            self.logger.error(f"Failed to load contract: {e}")
            return None
            
    def store_heartbeat(self, hb: Optional[SlowContractHeartbeat] = None) -> None:
        """Stores a SlowContractHeartbeat to persistent storage"""
        hb_to_store = self.latest_hb
        if hb:
            hb_to_store = hb
        if not hb_to_store: 
            raise Exception("Can't store hb if latest_hb is none!")
        
        if hb_to_store.FromNode == self.node.name:
            if hb_to_store.Status not in [ContractStatus.Created, 
                                   ContractStatus.TerminatedByAtn,
                                   ContractStatus.CompletedUnknownOutcome]:
                raise Exception(f"Does not store atn hb with status {hb_to_store.Status}")
        
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
       
        if scada_hb.Status == ContractStatus.CompletedUnknownOutcome:
            self.latest_hb = None # we can create new contract now!
            if self.can_create_contract():
                self.create_new_contract()
        elif scada_hb.Status == ContractStatus.TerminatedByScada:
            self.latest_hb = None
        else:
            self.latest_hb = scada_hb
    
    def create_new_contract(self) -> None:
        """
        - Create a new SlowDispatchContract at the top of the hour
        - Create a new Heartbeat, stores in latest_hb
        - Sends new Heartbeat to Scada
        """
        if self.next_contract_energy_wh is None:
            raise Exception("next_contract_energy_wh should not be None!")
        watthours = self.next_contract_energy_wh
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
            
        # Create contract starting at the next 5-minute boundary
        now = time.time()
        start_s = int(now - (now % 3600))

        oil_boiler_on = False
        if watthours > 0 and self.use_oil_as_fuel_substitute():
            watthours = 0
            if watthours > 2500:
                oil_boiler_on = True

        duration_minutes=60
        avg_power_watts = int(watthours * (60/duration_minutes))
        contract = SlowDispatchContract(
            ScadaAlias=self.layout.scada_g_node_alias,
            StartS=start_s,
            DurationMinutes=duration_minutes,
            AvgPowerWatts=avg_power_watts,
            OilBoilerOn=oil_boiler_on,
            ContractId=str(uuid.uuid4()),
        )
        
        # Create initial heartbeat
        hb = SlowContractHeartbeat(
            FromNode=self.node.name,
            Contract=contract,
            Status=ContractStatus.Created,
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
                    Dst=H0N.primary_scada,
                    Payload=self.latest_hb,
                )
            )

    def use_oil_as_fuel_substitute(self) -> bool:
        if self.latest_price is None:
            return False
        if self.latest_price.PriceUnit != MarketPriceUnit.USDPerMWh:
            raise Exception(f"Stop being so parochial and assuming {MarketPriceUnit.USDPerMWh}")
        price_usd_per_mwh = self.latest_price.PriceTimes1000 / 1000
        self.logger.info(f"Latest price is ${price_usd_per_mwh}/MWh. Fuel sub threshold ${self.settings.fuel_sub_usd_per_mwh}/MWh")
        if price_usd_per_mwh > self.settings.fuel_sub_usd_per_mwh and self.settings.fuel_substitution:
            return True
        elif not self.settings.fuel_substitution:
            self.logger.info("fuel_substation variable set to False! ")
            return False
        return False

    async def contract_heartbeat_task(self):
        """Task that sends regular heartbeats while a contract is active"""
        await asyncio.sleep(2)
        hb = self.initialize()
        if hb is not None:
            if hb.Status == ContractStatus.Created:
                # we didn't get any response, send again
                self.send_threadsafe(Message(Src=self.node.name,Dst=H0N.primary_scada,Payload=hb))
        while not self._stop_requested:
            try:
                # Only send heartbeats if we have an active contract              
                if self.latest_hb and self.latest_hb.Status in [ContractStatus.Created, ContractStatus.Received, ContractStatus.Active]:
                        # Check if contract has expired
                        if time.time() > self.latest_hb.Contract.contract_end_s():
                            # Contract expired - initiate completion
                            completion_hb = self.create_completion_heartbeat()
                            self.send_threadsafe(
                                Message(
                                    Src=self.node.name,
                                    Dst=H0N.primary_scada,
                                    Payload=completion_hb
                                )
                            )
                        else:
                            if self.latest_hb.Status == ContractStatus.Created: 
                                send_hb = self.latest_hb # RESEND first contract
                            else:
                                send_hb = self.create_midcontract_heartbeat() # Create a mid-contract heartbeat
                
                            self.send_threadsafe(
                                Message(
                                    Src=self.node.name,
                                    Dst=H0N.primary_scada,
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
            self.send_threadsafe(Message(Src=self.node.name, Dst=H0N.primary_scada,
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
            Status=ContractStatus.TerminatedByAtn,
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
            Status=ContractStatus.CompletedUnknownOutcome,
            Cause="Atn notes MarketSlot complete",
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
        if self.latest_hb.Status == ContractStatus.Created:
            return self.latest_hb # haven't gotten the Received ack yet
        elif self.latest_hb.Status in [ContractStatus.Received, ContractStatus.Active]:
                return SlowContractHeartbeat(
                    FromNode=self.node.name,
                    Contract=self.latest_hb.Contract,
                    Status=ContractStatus.Active,
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
        
        slot_start = datetime.datetime.fromtimestamp(
            hb.Contract.StartS, 
            tz=self.timezone
        ).strftime('%H:%M')

        slot_end = datetime.datetime.fromtimestamp(
            hb.Contract.contract_end_s(), 
            tz=self.timezone
        ).strftime('%H:%M')

        created_time = datetime.datetime.fromtimestamp(
            hb.MessageCreatedMs / 1000, 
            tz=self.timezone
        ).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        # Calculate total energy for the contract in Wh
        total_energy = hb.Contract.AvgPowerWatts * hb.Contract.DurationMinutes / 60
        
        # Energy used so far (only present in SCADA heartbeats)
        if hb.Status == ContractStatus.Created:
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

    
    