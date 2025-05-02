import asyncio
import time
import uuid
from datetime import datetime
from collections import deque
from typing import List, Sequence
from data_classes.house_0_names import H0CN, H0N
from gwproto.message import Message
from gwproactor.message import PatInternalWatchdogMessage
from gwproactor import MonitoredName, AppInterface
from gwproto.data_classes.sh_node import ShNode
from gwproto.enums import TelemetryName, RelayClosedOrOpen
from gwproto.named_types import AnalogDispatch, FsmFullReport
from result import Ok, Result

from actors.scada_actor import ScadaActor
from enums import LogLevel, TurnHpOnOff, HpModel, StratBossEvent, StratBossState
from named_types import (FsmEvent, Glitch, SingleMachineState, StratBossReady, StratBossTrigger)
from transitions import Machine


class StratBoss(ScadaActor):
    """Protects thermal stratification during heat pump transitions

    This actor manages system behavior during heat pump startup and defrost cycles to preserve
    valuable thermal stratification in storage and buffer tanks. It operates as part of the
    hierarchical state machine system with two states:

    - Dormant: Default state when stratification protection is not needed
    - Active: Actively managing relays & 010V actuators to protect stratification

    Activation is triggered by:
    1. Detection of heat pump defrost cycles through power and temperature patterns
    2. Receipt of HpTurningOn messages during heat pump startup

    The triggering activation is multi-stage:
      - StratBoss detects a stratification trigger and alerts its boss via a StratBossTrigger
      - The boss adjusts its command tree so that StratBoss has control over required relays and
      0-10V actuators (and, if needed, adjusts its own state machine)
      - The boss alerts StratBoss that its good to go, also via a StratBossTrigger.

    When activated, it:
    1. Takes control of the store charge/discharge relay and thermostat relays
    2. Configures the system to circulate through distribution rather than storage or buffer
    43 Maintains this configuration until
        - heat pump normalizes (as detected by a reasonable lift), or
        - HpTurningOff message received, or
        - its boss tells it to turn off 
        - A longish timer times out (e.g. ~12 minutes)

    This helps prevent mixing of stratified layers during periods when the heat pump is 
    circulating water but not actively heating it. Since this is a hydronic system it does
    not annoy residents the way blowing cold air does in defrost for air-to-air HPs - the
    circulating water is likely still above room temperature, just not enough to actively heat.

    """
    TIMEOUT_MINUTES = 20
    
    DIST_PUMP_ON_SECONDS = 45 # time it takes to get the distributin pump on when its off
    VALVED_TO_DISCHARGE_SECONDS = 30 # time it takes to go from valve in charge -> valve in discharge
    LG_HYDROKIT_PRIMARY_PUMP_DELAY_SECONDS = 120 # TODO: move into hardware layout
    SAMSUNG_HYDROKIT_PRIMARY_PUMP_DELAY_SECONDS = 0
    DEFROST_DETECT_SLEEP_S = 2 # for the strat watcher as it tracks
    LIFT_DETECT_SLEEP_S = 5
    HP_LIFT_THRESHOLD_F = 15
    HP_POWER_THRESHOLD_W = 7000
    WATCHDOG_PAT_S = 60

    states = StratBossState.values()

    transitions = [
        # Dormant -> Active triggers
        {"trigger": "HpTurnOnReceived", "source": "Dormant", "dest": "Active"},
        {"trigger": "DefrostDetected", "source": "Dormant", "dest": "Active"},
        # Active -> Dormant triggers
        {"trigger": "LiftDetected", "source": "Active", "dest": "Dormant"},
        {"trigger": "HpTurnOffReceived", "source": "Active", "dest": "Dormant"},
        {"trigger": "Timeout", "source": "Active", "dest": "Dormant"},
        {"trigger": "BossCancels", "source": "Active", "dest": "Dormant"},
    ]

    def __init__(self, name: str, services: AppInterface):
        super().__init__(name, services)
        self._stop_requested: bool = False
        self.hp_model = self.settings.hp_model # TODO: will move to hardware layout
        self.primary_pump_delay_seconds: int = self.get_primary_pump_delay_seconds()
        self.state: StratBossState = StratBossState.Dormant
        self.machine = Machine(
            model=self,
            states=StratBoss.states,
            transitions=StratBoss.transitions,
            initial=StratBossState.Dormant,
            send_event=False
        )
        
        self.idu_w_readings = deque(maxlen=15)
        self.odu_w_readings = deque(maxlen=15)
        self.hp_power_w: float = 0
        self.ewt_f: float = 0
        self.lwt_f: float = 0
        self.hp_scada_ops_relay_state: RelayClosedOrOpen = RelayClosedOrOpen.RelayOpen
        self.log(f"Exempt zones: {self.layout.strat_boss_exemption_zones}")
        self.log(f"Hours exempt: {self.layout.strat_boss_exemption_hours}")

    def start(self) -> None:
        self.services.add_task(
            asyncio.create_task(
                self.defrost_watcher(), name="defrost_watcher"
            )
        )
        if self.never_operates():
            self._send_to(self.atn,
                          Glitch(
                              FromGNodeAlias=self.layout.scada_g_node_alias,
                              Node=self.node.name,
                              Type=LogLevel.Info,
                              Summary="StratBoss not running. All zones exempt all the time!",
                              Details="",
                          ))
            self.log("Strat boss not running. All zones exempt!")

    def stop(self) -> None:
        """ Required method, used for stopping tasks. Noop"""
        self._stop_requested = True

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""
        ...

    def never_operates(self) -> bool:
        """ To shut down strat boss, list all 24 hours 0 .. 23 as exemption
        hours and all zones as exemption zones"""
        if len(set(self.layout.strat_boss_exemption_hours)) == 24 and \
            set(self.layout.zone_list).issubset(set(self.layout.strat_boss_exemption_zones)):
                return True
        else:
            return False

    def operating_now(self) -> bool:
        if len(self.strat_zones_now()) == 0:
            return False
        return True
    
    def strat_zones_now(self) -> List[str]:
        """Returns the list of zones used for cycling water from the heat pump
        through when in strat boss"""
        now = datetime.now(self.timezone)
        exempted = []
        if now.hour in self.layout.strat_boss_exemption_hours:
            exempted = self.layout.strat_boss_exemption_zones
        
        return [zone for zone in self.layout.zone_list if zone not in exempted]

    def sidelined(self) -> bool:
        """ Sidelined if it is out of the chain of command; e.g boss is own ShNode"""
        if self.boss == self.node:  # not in the command tree
            return True
        return False

    def get_primary_pump_delay_seconds(self) -> int:
        """Seconds between closing the HpOps relay and primary pump coming on
        """
        if self.hp_model in  [HpModel.SamsungFourTonneHydroKit, HpModel.SamsungFiveTonneHydroKit]:
            return self.SAMSUNG_HYDROKIT_PRIMARY_PUMP_DELAY_SECONDS
        elif self.hp_model == HpModel.LgHighTempHydroKitPlusMultiV:
            return self.LG_HYDROKIT_PRIMARY_PUMP_DELAY_SECONDS
        else:
            raise Exception(f"Don't have primary pump delay seconds for {self.hp_model}!")

    def strat_prep_seconds(self) -> int:
        """
        Seconds required before Charge/Discharge valved to discharge and dist pump on full
        """
        # TODO: check current valve and pump state first
        return max(self.DIST_PUMP_ON_SECONDS, self.VALVED_TO_DISCHARGE_SECONDS)

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        if self.never_operates():
            return Ok(False)
        
        if self.sidelined():
            self.log(f"Sidelined so ignoring messages! Handle: {self.node.handle}")
            return Ok(False)
        payload = message.Payload
        from_node = self.layout.node(message.Header.Src, None)
        if from_node is None:
            return Ok(False)
        match payload:
            case FsmEvent():
                try:
                    self.process_fsm_event(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_fsm_event: {e}")
            case FsmFullReport():
                ... # direct reports following up re acting on commands given
            case SingleMachineState():
                self.process_single_machine_state(from_node, payload)
            case StratBossTrigger():
                self.process_strat_boss_trigger(from_node, payload)
            case _: 
                self.log(f"{self.name} received unexpected message: {message.Header}"
                )
                return Ok(False)
        return Ok(True)

    def process_fsm_event(self, from_node: ShNode, payload: FsmEvent) -> None:
        if from_node != self.hp_relay_boss:
            self.log(f"Rejecting FsmEvent. Expected from_node hp_relay_boss but got {from_node.Name}")
        if payload.ToHandle != self.hp_relay_boss.Handle:
            self.log(f"Rejecting FsmEvent. Excected ToHandle {self.hp_relay_boss.Handle:} but got {payload.ToHandle}")
        if payload.EventType == TurnHpOnOff.enum_name():
            let_boss_know = False
            if payload.EventName == TurnHpOnOff.TurnOn \
                and self.state == StratBossState.Dormant \
                and self.operating_now():
                    if self.hp_scada_ops_relay_state == RelayClosedOrOpen.RelayClosed:
                        self.log("NOT STARTING STRATBOSS: hp scada ops relay is already closed")
                    else:
                        let_boss_know = True
                        trigger = StratBossTrigger(
                            FromState=StratBossState.Dormant,
                            ToState=StratBossState.Active,
                            Trigger=StratBossEvent.HpTurnOnReceived
                        )
            elif payload.EventName == TurnHpOnOff.TurnOff \
                and self.state == StratBossState.Active:
                let_boss_know = True
                trigger = StratBossTrigger(
                    FromState=StratBossState.Active,
                    ToState=StratBossState.Dormant,
                    Trigger=StratBossEvent.HpTurnOffReceived,
                )
            if let_boss_know:
                self.log(f"Sending {trigger.Trigger} to {self.boss.Handle}")
                self._send_to(self.boss, trigger)
            else:
                self.log(f"Got {payload.EventName} but its not triggering a state change from {self.state}")    

    def process_single_machine_state(self, from_node: ShNode, sms: SingleMachineState):
        if from_node == self.hp_scada_ops_relay:
            if sms.State != self.hp_scada_ops_relay_state:
                self.log(f"HpScadaOpsRelay is {sms.State}!")
                self.hp_scada_ops_relay_state = RelayClosedOrOpen(sms.State)
                # When Scada starts up the relay is closed (de-energized)
                # and this should start StratBoss, even though HpRelayBoss
                # is not involved 
                if sms.State == RelayClosedOrOpen.RelayClosed and self.state == StratBossState.Dormant:
                    self._send_to(self.boss,
                                  StratBossTrigger(
                            FromState=StratBossState.Dormant,
                            ToState=StratBossState.Active,
                            Trigger=StratBossEvent.HpTurnOnReceived
                        ))

    def process_strat_boss_trigger(self, from_node: ShNode, payload: StratBossTrigger):
        """
        Receiving this message from the boss means the command tree reflects ToState
        """
        if self.boss != from_node:
            self.log(f"Ignoring trigger from {from_node.handle}. My handle is {self.node.handle}") # todo: send glitch
            return
        if payload.FromState != self.state:
            self.log(f"Ignoring trigger. payload.FromState {payload.FromState} and self.state {self.state}")
            return
        self.pull_trigger(payload)
        
        if payload.Trigger == StratBossEvent.HpTurnOnReceived:
            asyncio.create_task(self._ungate_hp_relay_boss())

    def pull_trigger(self, trigger: StratBossTrigger):
        if trigger.FromState != self.state:
            return
        
        before = self.state
        if trigger.Trigger == StratBossEvent.HpTurnOnReceived:
            self.HpTurnOnReceived()
        elif trigger.Trigger == StratBossEvent.DefrostDetected:
            self.DefrostDetected()
        elif trigger.Trigger == StratBossEvent.LiftDetected:
            self.LiftDetected()
        elif trigger.Trigger == StratBossEvent.HpTurnOffReceived:
            self.HpTurnOffReceived()
        elif trigger.Trigger == StratBossEvent.Timeout:
            self.Timeout()
        elif trigger.Trigger == StratBossEvent.BossCancels:
            self.BossCancels()
        else:
            self.log(f"DON'T KNOW TRIGGER {trigger.Trigger}") # TODO: add Glitch
        self.log(f"StratBoss state change: {trigger.Trigger}: {before} -> {self.state}")
        if before != self.state:
            self._send_to(self.primary_scada,
                          SingleMachineState(
                              MachineHandle=self.node.handle,
                              StateEnum=StratBossState.enum_name(),
                              State=self.state,
                              Cause=trigger.Trigger.value,
                              UnixMs=int(time.time() * 1000)
                          ))
        if self.state == StratBossState.Active:
            self._timeout_timer_task = asyncio.create_task(self._timeout_timer())
            asyncio.create_task(self.active(trigger.Trigger))
        else:
            self.flush_lift_timer()
            self.flush_timeout_timer()

    def turn_on_dist_pump(self) -> None:
        """
        Turn on heat calls for all zones - EXCEPT those in the StratBossExemptionZones list
        and set 010V for dist pump to 100
        """
        self.log(f"Forcing heatcalls for {self.strat_zones_now()}")
        # start heat calls on all white wires
        for zone in self.strat_zones_now():
            self.heatcall_ctrl_to_scada(zone)
            self.stat_ops_close_relay(zone)
        # caleffi zone valve controller takes about 30 seconds CHECK
        dist_010v_node = self.layout.node(H0N.dist_010v)
       
        
        if datetime.now(self.timezone).hour in self.layout.strat_boss_exemption_hours:
            dist_010_value = self.layout.exempted_strat_boss_dist_010v
            self.log(f"Sent exemption value {dist_010_value} to {dist_010v_node.handle}")
        else:
            dist_010_value = self.data.ha1_params.StratBossDist010
            self.log(f"Sending normal {dist_010_value} to {dist_010v_node.handle} ")
        self._send_to(
            dist_010v_node,
            AnalogDispatch(
                FromHandle=self.node.handle,
                ToHandle=dist_010v_node.handle,
                AboutName=dist_010v_node.Name,
                Value=dist_010_value,
                TriggerId=str(uuid.uuid4()),
                UnixTimeMs=int(time.time() * 1000),
            )
        )
       

    def flush_timeout_timer(self) -> None:
        if hasattr(self, "_timeout_timer_task"):
            task = self._timeout_timer_task
            if not task.done():  # Check if it's still running
                task.cancel()  # Request cancellation
            del self._timeout_timer_task # Remove the attribute

    def flush_lift_timer(self) -> None:
        if hasattr(self, "_lift_timer_task"):
            task = self._lift_timer_task
            if not task.done():  # Check if it's still running
                task.cancel()  # Request cancellation
            del self._lift_timer_task  # Remove the attribute

    async def active(self, trigger: StratBossEvent) -> None:
        if trigger == StratBossEvent.HpTurnOnReceived:
            max_strat_prep_seconds = max(self.DIST_PUMP_ON_SECONDS, self.VALVED_TO_DISCHARGE_SECONDS)
            wait_s = self.primary_pump_delay_seconds - max_strat_prep_seconds # could be ~75 s for LG
            if wait_s > 5:
                wait_s = wait_s - 5
                self.log(f"Waiting {wait_s} s before changing relays")
                await asyncio.sleep(wait_s)

        #Make sure we're still active before proceeding in case we waited.
        if self.state == StratBossState.Active:
            self.valved_to_discharge_store()
            self.turn_on_dist_pump()
            self._lift_timer_task = asyncio.create_task(self._lift_timer())

    async def _ungate_hp_relay_boss(self) -> None:
        wait_seconds = max(0, self.strat_prep_seconds() - self.primary_pump_delay_seconds)
        self.log(f"Pump delay seconds {self.primary_pump_delay_seconds} and strat prep seconds {self.strat_prep_seconds()}")
        if wait_seconds > 0:
            self.log(f"Waiting {wait_seconds} s before ungating HpRelayBoss")
            await asyncio.sleep(wait_seconds)
        self.log("StratBossReady to Hp RelayBoss!")
        self._send_to(self.hp_relay_boss, StratBossReady())

    async def _lift_timer(self) -> None:
        """ Wait 2 minutes. Then if LWT - EWT > Lift Threshold send trigger"""
        self.log("sleeping for 2 minutes before attempting to detect lift")
        await asyncio.sleep(2*60)

        log_counter = 0 # Counter to track logging frequency
        LOG_INTERVAL = 30 # Log every 30 seocnds
        while self.state == StratBossState.Active:
            if self.update_temp_readings():
                lift = self.lwt_f-self.ewt_f
                if log_counter % (LOG_INTERVAL // self.LIFT_DETECT_SLEEP_S) == 0:
                    self.log(f"lwt {round(self.lwt_f, 2)} F, ewt {round(self.ewt_f, 2)} F, lift {round(lift)} F v {self.HP_LIFT_THRESHOLD_F} ")
                if lift > self.HP_LIFT_THRESHOLD_F:
                        self._send_to(self.boss,StratBossTrigger(
                            FromState=StratBossState.Active,
                            ToState=StratBossState.Dormant,
                            Trigger=StratBossEvent.LiftDetected
                        ))
                        self.log(f"Lift detected! {round(lift)} F  ")
            else:
                self.log("No data from ewt and/or lwt and/or ho_idu_pwr and/or hp_odu_pwr!")
            log_counter += 1
            await asyncio.sleep(self.LIFT_DETECT_SLEEP_S)

    async def _timeout_timer(self) -> None:
        """ Wait 12 minutes. If still active at the end then pull the ActiveTwelveMinutes Trigger"""
        await asyncio.sleep(self.TIMEOUT_MINUTES * 60)
        if self.state == StratBossState.Active:
            self.log(f"Letting boss know its time to go dormant: Timeout event after {self.TIMEOUT_MINUTES}")
            self._send_to(self.boss, StratBossTrigger(
                FromState=StratBossState.Active,
                ToState=StratBossState.Dormant,
                Trigger=StratBossEvent.Timeout
            ))

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.WATCHDOG_PAT_S * 10)]

    async def defrost_watcher(self) -> None:
        """
        Responsible for helping to detect and triggering the defrost state change
        """
        self.last_pat_s = 0
        while not self._stop_requested:
            if self.operating_now():
                if time.time() - self.last_pat_s > self.WATCHDOG_PAT_S:
                    self._send(PatInternalWatchdogMessage(src=self.name))
                    self.last_pat_s = time.time()
                try: 
                    good_readings = self.update_power_readings()
                except Exception as e:
                    self.log(f"Trouble with update_power_readings: {e}")
                if good_readings:
                    if self.state == StratBossState.Dormant:
                        if self.hp_model == HpModel.LgHighTempHydroKitPlusMultiV:
                            if self.lg_high_temp_hydrokit_entering_defrost():
                                self._send_to(self.boss, StratBossTrigger(
                                        FromState=StratBossState.Dormant,
                                        ToState=StratBossState.Active,
                                        Trigger=StratBossEvent.DefrostDetected
                                    ) 
                                )
                                self.log("Defrost detected!")
                        elif self.hp_model in [HpModel.SamsungFourTonneHydroKit,
                                            HpModel.SamsungFiveTonneHydroKit]:
                            if self.samsung_entering_defrost():
                                self._send_to(self.boss, StratBossTrigger(
                                    FromState=StratBossState.Dormant,
                                        ToState=StratBossState.Active,
                                        Trigger=StratBossEvent.DefrostDetected
                                    )
                                )
                                self.log("Defrost detected!")

                await asyncio.sleep(self.DEFROST_DETECT_SLEEP_S)

    def lg_high_temp_hydrokit_entering_defrost(self) -> bool:
        """
        The Lg High Temp Hydrokit is entering defrost if:  
          - Indoor Unit Power > Outdoor Unit Power and
          - IDU Power going up and
          - ODU power going down
        """
        entering_defrost = True
        if self.odu_w_readings[-1] > self.idu_w_readings[0]:
            entering_defrost = False
        elif self.idu_w_readings[-1] <= self.idu_w_readings[0]: # idu not going up
            entering_defrost = False
        elif self.odu_w_readings[-1] >= self.odu_w_readings[0]: # odu not going down
            entering_defrost = False
        return entering_defrost
    
    def samsung_entering_defrost(self) -> bool:
        """
        The Samsung High Temp Hydrokit is entering defrost if:  
          - IDU Power  - ODU Power > 1500
          - ODU Power < 500
        """
        entering_defrost = True
        if self.idu_w_readings[-1] - self.odu_w_readings[-1] < 1500:
            entering_defrost = False
        elif self.odu_w_readings[-1] > 500:
            entering_defrost = False
        return entering_defrost

    def update_temp_readings(self) -> bool:
        ewt_channel = self.layout.channel(H0CN.hp_ewt)
        lwt_channel = self.layout.channel(H0CN.hp_lwt)
         # TODO: add these channels to the test objects!
        if ewt_channel is None:
            return False
        assert ewt_channel.TelemetryName == TelemetryName.WaterTempCTimes1000
        assert lwt_channel.TelemetryName == TelemetryName.WaterTempCTimes1000
        if ewt_channel.Name not in self.data.latest_channel_values:
            return False
        if lwt_channel.Name not in self.data.latest_channel_values:
            return False
        self.ewt_f = c_to_f(self.data.latest_channel_values[ewt_channel.Name] / 1000)
        self.lwt_f = c_to_f(self.data.latest_channel_values[lwt_channel.Name] / 1000)
        return True

    def update_power_readings(self) -> bool:
        odu_pwr_channel = self.layout.channel(H0CN.hp_odu_pwr)
        idu_pwr_channel = self.layout.channel(H0CN.hp_idu_pwr)
        assert odu_pwr_channel.TelemetryName == TelemetryName.PowerW
        if odu_pwr_channel.Name not in self.data.latest_channel_values:
            return False
        if idu_pwr_channel.Name not in self.data.latest_channel_values:
            return False
        odu_pwr = self.data.latest_channel_values[odu_pwr_channel.Name]
        idu_pwr = self.data.latest_channel_values[idu_pwr_channel.Name]
        if (odu_pwr is None) or (idu_pwr is None):
            return False 
        self.hp_power_w = odu_pwr + idu_pwr
        self.odu_w_readings.append(odu_pwr)
        self.idu_w_readings.append(idu_pwr)
        return True

def c_to_f(temp_c: float) -> float:
    return (9*temp_c/5) + 32

