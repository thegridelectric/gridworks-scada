import json
import random
import time
import datetime
from pathlib import Path
from typing import Optional

import pytz
from gwsproto.data_classes.house_0_layout import House0Layout
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import SlowDispatchContractStatus
from gwproactor.logger import LoggerOrAdapter
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.named_types import  SlowContractHeartbeat


from actors.config import ScadaSettings


class ContractHandler:
    """Handles SCADA's representation contract and dispatch contracts w Atn"""

    DONE_STATES = [
        SlowDispatchContractStatus.TerminatedByLtn,
        SlowDispatchContractStatus.TerminatedByScada,
        SlowDispatchContractStatus.CompletedUnknownOutcome,
        SlowDispatchContractStatus.CompletedSuccess,
        SlowDispatchContractStatus.CompletedFailureByLtn,
        SlowDispatchContractStatus.CompletedFailureByScada,
    ]
    GRACE_PERIOD_MINUTES = 5  # Time after contract end before auto-ready
    WARNING_MINUTES_AFTER_END  = 2 

    LOGGER_NAME = "ContractHandler"
    def __init__(
        self,
        settings: ScadaSettings,
        layout: House0Layout,
        node: ShNode,  # intended to be H0N.primary_scada
        logger: LoggerOrAdapter,
    ):
        self.settings = settings
        self.layout = layout
        self.node = node
        self.timezone = pytz.timezone(self.settings.timezone_str)
        self.logger = logger
        self.contract_file = Path(
            f"{self.settings.paths.data_dir}/slow_dispatch_contract.json"
        )
        self.latest_scada_hb: Optional[SlowContractHeartbeat] = None
        self.prev: Optional[SlowContractHeartbeat] = None
        self.latest_power_w: int = 0
        self.energy_used_wh: float = 0
        self.energy_updated_s: Optional[float] = None

    def update_energy_usage(self, latest_power_w: int) -> None:
        """Updates the live dispatch contract (self.latest_scada_hb.contract)
        """
        now = time.time()
        if not self.latest_scada_hb:
            return
        if self.energy_updated_s is None:
            self.energy_used_wh = 0
            self.energy_updated_s = now
            self.latest_power_w = latest_power_w
            self.logger.info("Race condition! latest_scada_hb existed but energy_updated_s was 0")
            return
        
        delta_s = now - self.energy_updated_s
        self.energy_updated_s = now
        delta_wh = self.latest_power_w * delta_s / 3600
        self.energy_used_wh += delta_wh
        self.latest_power_w = latest_power_w

    @property
    def remaining_watthours(self) -> Optional[int]:
        """ If there is no live contract, returns None

        Otherwise return remaining WattHours left in contract, with
        a minimum of 0
        """
        if not self.latest_scada_hb:
            return None
        contracted_wh = int(self.latest_scada_hb.Contract.AvgPowerWatts * self.latest_scada_hb.Contract.DurationMinutes/60)
        return max(int(contracted_wh - self.energy_used_wh), 0)

    def active_contract_has_expired(self) -> bool:
        if not self.latest_scada_hb:
            return False
        if time.time() > self.latest_scada_hb.Contract.contract_end_s():
            return True
        return False


    def load_heartbeat(self) -> Optional[SlowContractHeartbeat]:
        """Loads existing SlowDispatchContract from persistent storage

        - Returns a new SlowDispatchContract with state CompletedUnknownOutcome
        if the passing of time mandates a state change.
        - If the hb doesn't exist, doesn't load anything and returns None
        - If the hb exists and covered by current time, sets self.hb
        to this heartbeat and returns None
        """
        if not self.contract_file.exists():  # no file
            self.logger.info("No contract")
            return None
        with open(self.contract_file, "r") as f:
            contract_data = json.load(f)

        try:
            hb = SlowContractHeartbeat.model_validate(contract_data)
            if hb.FromNode == H0N.ltn:
                if hb.Status not in [SlowDispatchContractStatus.TerminatedByLtn,
                                     SlowDispatchContractStatus.CompletedUnknownOutcome]:
                    return
                self.prev = hb
            else:
                if time.time() > hb.Contract.contract_end_s():
                    if hb.Status not in self.DONE_STATES:
                        self.prev = SlowContractHeartbeat(
                            FromNode=self.node.name,
                            Contract=hb.Contract,
                            PreviousStatus=hb.Status,
                            Status=SlowDispatchContractStatus.CompletedUnknownOutcome,
                            WattHoursUsed=hb.WattHoursUsed,
                            MessageCreatedMs=int(time.time() * 1000),
                            Cause="Set by Scada on rebooting",
                            YourLastDigit=hb.MyDigit,
                            MyDigit=random.choice(range(10)),
                        )
                        self.logger.info(
                            "Contract expired! Should send hb to atn ASAP."
                            "Loaded ContractHb into prev"
                        )
                        return self.prev
                    else:
                        return None
                else:
                    if hb.WattHoursUsed is None:
                        raise ValueError("Cannot happen: from scada -> WattHoursUsed not None")
                    self.latest_scada_hb = hb
                    self.energy_used_wh = hb.WattHoursUsed
                    self.energy_updated_s = time.time()
                    self.logger.info("Loaded ContractHb into hb")
                    return hb
        except Exception as e:
            raise ValueError(f"Issue loading contract! {e}")
            # self.logger.warning(f"Issue loading contract! {e}")

    def store_heartbeat(self, atn_hb: Optional[SlowContractHeartbeat] = None) -> None:
        """Stores  SlowDispatchContract to persistent storage

          - In default atn_hb None case, stores self.latest_scada_hb
          - 
        """
        if self.latest_scada_hb is None:
            raise ValueError("Do not expect to store_heartbeat when None")
        hb = self.latest_scada_hb
        if atn_hb:
            if atn_hb.Status not in [SlowDispatchContractStatus.TerminatedByLtn,
                                     SlowDispatchContractStatus.CompletedUnknownOutcome]:
                raise ValueError("only stores atn_hb's with Status TerminatedByLtn or CompletedUnknownAutcome")
            hb = atn_hb

        with open(self.contract_file, "w") as f:
            # Store the JSON rep of hb
            f.write(hb.model_dump_json(indent=4))

    def initialize(self) -> Optional[SlowContractHeartbeat]:
        """Set initial status and contract state based on persistent store.

        Returns a heartbeat if contract has become expired
        """
        return_hb = self.load_heartbeat()  # None unless returning expired HB to atn
        if return_hb:
            self.logger.info(f"Starting with contract {return_hb.Contract.ContractId[:3]}")
        else:
            self.logger.info("Starting with no contract")
        return return_hb

    def flush_latest_scada_hb(self) -> None:
        """ Sets latest_scada_hb to None, energy_used_wh to 0
        and energy_updated_s to None
        """
        if not self.latest_scada_hb:
            return
        if self.latest_scada_hb.Status not in self.DONE_STATES:
            return
        self.latest_scada_hb = None
        self.energy_used_wh = 0
        self.energy_updated_s = None

    def get_initial_watt_hours(self, atn_hb: SlowContractHeartbeat) -> int:
        """Contracts start within 10 seconds of market so returns
        delta_t * latest_power_w
        """
        delta_s = (atn_hb.MessageCreatedMs/1000) - atn_hb.Contract.StartS
        return int(self.latest_power_w * delta_s/3600)

    def start_new_contract_hb(
        self, atn_hb: SlowContractHeartbeat
    ) -> SlowContractHeartbeat:
        """Managesthe first HB for a newly created Contract
          -  cases:
            - Prev contract exists, terminated and/or completed, inside the grace period
            - Existing contract is not completed or terminated, still
            in the existing timeframe: Ignore this one
            - Previous contract exists, outside of grace period 
            - No previous contract
            - right now does not handle a contract for a future time slot
        """

        if atn_hb.Status != SlowDispatchContractStatus.Created:
            raise Exception(
                f"Can only start new contract with a SlowDispatchContractStatus of Created, not {atn_hb.Status}"
            )
        if self.latest_scada_hb:
            self.logger.warning("Ignoring atn hb! Still inside existing contract")
            self.logger.warning(f"Existing: {self.latest_scada_hb}")
            raise Exception(f"Inbound: {atn_hb}")
        
        now = time.time()
        self.energy_used_wh = self.get_initial_watt_hours(atn_hb)
        self.energy_updated_s = now
        self.latest_scada_hb = SlowContractHeartbeat(
            FromNode=self.node.Name,
            Contract=atn_hb.Contract,
            PreviousStatus=atn_hb.Status,
            Status=SlowDispatchContractStatus.Received,
            WattHoursUsed=round(self.energy_used_wh),
            MessageCreatedMs=int(now * 1000),
            MyDigit=random.choice(range(10)),
            YourLastDigit=atn_hb.MyDigit,
        )
        self.store_heartbeat()
        return self.latest_scada_hb

    def update_existing_contract_hb(
        self, atn_hb: SlowContractHeartbeat
    ) -> Optional[SlowContractHeartbeat]:
        """ Update energy usage and 
        - return  hb for Scada to send back
        - or None if Scada doesn't send anything back (if Atn terminates contract
        prior to completion)

        raise exception if latest_scada_hb is none or if its contract
        does not match
        """
        self.update_energy_usage(self.latest_power_w)

        if atn_hb.Status == SlowDispatchContractStatus.Created:
            raise Exception("Does not process newly created contracts!")
        if self.latest_scada_hb is None:
            raise Exception(
                "Do not call update_existing_contract_hb if latest_atn_hb is None"
            )
        if self.latest_scada_hb.Contract != atn_hb.Contract:
            raise Exception(
                "Do not call update_existing_contract if self.hb.Contract != atn_hb.Contract"
            )
        if atn_hb.Status == SlowDispatchContractStatus.TerminatedByLtn:  # clear out contract
            self.store_heartbeat(atn_hb) 
            self.flush_latest_scada_hb()
            self.prev = atn_hb
            return None
        elif atn_hb.Status == SlowDispatchContractStatus.CompletedUnknownOutcome:
            # Determine contracted energy amount
            contracted_energy_wh = atn_hb.Contract.AvgPowerWatts * atn_hb.Contract.DurationMinutes / 60
            # Send final energy accounting

            final_hb = self.scada_contract_completion_hb(
                cause=f"Final energy accounting: used {self.energy_used_wh}Wh of contracted {contracted_energy_wh}Wh")
            self.latest_scada_hb = final_hb
            self.store_heartbeat() # stores latest_scada_hb
            self.flush_latest_scada_hb() # then fluses it
            self.prev = final_hb
            return final_hb
        elif atn_hb.Status in [SlowDispatchContractStatus.Confirmed, SlowDispatchContractStatus.Active]:
            self.latest_scada_hb = SlowContractHeartbeat(
                FromNode=H0N.primary_scada,
                Contract=atn_hb.Contract,
                PreviousStatus=atn_hb.Status,
                Status=SlowDispatchContractStatus.Active,
                WattHoursUsed=round(self.energy_used_wh),
                MessageCreatedMs=int(time.time() * 1000),
                MyDigit=random.choice(range(10)),
                YourLastDigit=atn_hb.MyDigit,
            )
            self.store_heartbeat()
            return self.latest_scada_hb
        else:
            raise ValueError(f"Unexpected status from atn_hb: {atn_hb.Status}")

    def scada_terminates_contract_hb(self, cause: str = "") -> SlowContractHeartbeat:
        """Creats a heartbeat declaring scada termination of contract
        - can only call if self.latest_scada_hb exists
        - sets prev to terminating_hb  and latest_scada_hb to None
        """
        if not self.latest_scada_hb:
            raise Exception("Cannot call scada terminates contract if no latest_scada_hb")
        hb = SlowContractHeartbeat(
            FromNode=self.node.Name,
            Contract=self.latest_scada_hb.Contract,
            PreviousStatus=self.latest_scada_hb.Status,
            Status=SlowDispatchContractStatus.TerminatedByScada,
            Cause=cause,
            WattHoursUsed=round(self.energy_used_wh),
            MessageCreatedMs=int(time.time() * 1000),
            MyDigit=random.choice(range(10)),
            YourLastDigit=self.latest_scada_hb.MyDigit,
        )
        self.prev = hb
        self.latest_scada_hb = None
        return hb

    def scada_contract_completion_hb(self, cause="") -> SlowContractHeartbeat:
        """Creats a heartbeat noting time has passed completion
        - can only call if self.latest_scada_hb exists
        - sets prev to this hb and latest_scada_hb to None

        Raises exception if called before the ContractEndS
        """
        now = time.time()
        if not self.latest_scada_hb:
            raise Exception("Cannot call scada terminates contract if no latest_atn_hb")
        if now < self.latest_scada_hb.Contract.contract_end_s():
            raise Exception(
                f"scada_detects_contract_complete_hb called at {int(now)}, before ContractEndTime of {self.latest_scada_hb.Contract.contract_end_s()}"
            )
        hb = SlowContractHeartbeat(
            FromNode=self.node.Name,
            Contract=self.latest_scada_hb.Contract,
            PreviousStatus=self.latest_scada_hb.Status,
            Status=SlowDispatchContractStatus.CompletedUnknownOutcome,
            Cause=cause,
            WattHoursUsed=round(self.energy_used_wh),
            MessageCreatedMs=int(time.time() * 1000),
            MyDigit=random.choice(range(10)),
            YourLastDigit=self.latest_scada_hb.MyDigit,
            IsAuthoritative=False # not claiming authority on outcome
        )
        self.prev = hb
        self.latest_scada_hb = None
        return hb

    def formatted_contract(self, hb_to_format: Optional[SlowContractHeartbeat] = None) -> str:
        """Format contract heartbeat information for logging in a human-readable format."""
        hb = self.latest_scada_hb
        if hb_to_format:
            hb = hb_to_format
        
        if not hb:
            return ""
        
        # Convert time to local timezone
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
        if hb.Status == SlowDispatchContractStatus.Created:
            energy_used = 0
        else:
            energy_used = f"{round(self.energy_used_wh, 1)}"
        
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

