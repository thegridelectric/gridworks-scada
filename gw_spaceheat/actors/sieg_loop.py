import time
from datetime import datetime
from typing import List, Optional, Sequence
import asyncio
import uuid
from collections import deque
from enum import auto
from data_classes.house_0_names import H0CN
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto.enums import TelemetryName, StoreFlowRelay
from gwproto.message import Message
from gwproto.data_classes.sh_node import ShNode
from gwproto.named_types import FsmFullReport, SingleReading, AnalogDispatch
from result import Ok, Result
from gw.enums import GwStrEnum
from transitions import Machine
from actors.hp_boss import SiegLoopReady, HpBossState
from actors.scada_actor import ScadaActor
from actors.scada_interface import ScadaInterface
from enums import HpModel, LogLevel
from named_types import (ActuatorsReady, Glitch, ResetHpKeepValue, SetLwtControlParams,
    SetTargetLwt, SiegTargetTooLow,  SingleMachineState)

from transitions import Machine
class SiegValveState(GwStrEnum):
    KeepingMore = auto()
    KeepingLess = auto()
    SteadyBlend = auto()
    FullySend = auto()
    FullyKeep = auto() 

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "sieg.valve.state"
    
class ValveEvent(GwStrEnum):
    StartKeepingMore = auto()
    StartKeepingLess = auto()
    StopKeepingMore = auto()
    StopKeepingLess = auto()
    ResetToFullySend = auto()
    ResetToFullyKeep = auto()

class SiegControlState(GwStrEnum):
    Initializing = auto() # Scada just started up
    Dormant = auto()  # Heat pump off
    MovingToStartupHover = auto()  # Moving to t2 position 
    MovingToFullSend = auto() # 
    StartupHover = auto()  # Waiting at t2 position
    PID = auto()  # Normal proportional control
    Defrost = auto() # Going through defrost

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "sieg.control.state"

class ControlEvent(GwStrEnum):
    Blind = auto()
    DefrostDetected = auto()
    InitializationComplete = auto()
    HpTurnsOff = auto()
    HpPreparing = auto()
    LeavingDefrostDetected = auto()
    LeaveStartupHover = auto()
    ReachT2 = auto()
    ReachFullSend = auto()


class SiegLoop(ScadaActor):
    """
    ```
              ├── HpLoopOnOff relay
              └── HpLoopKeepSend relay
    ```
    SiegLoop: Heat Pump Leaving Water Temperature Control System

    This class manages a Siegenthaler loop valve which controls the mixing ratio between:
    1. Water recirculating directly back to the heat pump (keep path)
    2. Water flowing to the heating distribution system (send path)

    Control Problem:
    ---------------
    The primary objective is to maintain a target leaving water temperature (LWT) from the heat 
    pump while optimizing overall system efficiency. The challenge involves:

    1. Physical Characteristics:
    - Recirculation loop (~7 feet of 1" pipe) with ~4 second travel time
    - Temperature sensors with ~10 second response time
    - Valve movement takes ~70 seconds for full 0-100% travel

    2. System Dynamics:
    - At 100% keep: All water recirculates back to heat pump, increasing LWT
    - At 0% keep: All water sent to distribution; LWT set by HP lift
    - System has inherent thermal lag and momentum

    Control Algorithm:
    ----------------
    The system implements a hybrid model-based + PID control strategy:

    1. When the heat pump starts up, the valve stays fully closed and then
    attempts to nail the appropriate position to get the correct leaving
    water temperature, given the current lift and entering water temp

    2. PID. After that, the heat pump uses a classic PID mechanism, adjusting
    the valve position every 30 seconds. 

    Recalibration of Percent Keep
    -----------------
    - The valve position is controlled by two relays. One (`hp_loop_on_off`)
    determines if the valve is moving. The other determines what direction 
    it is moving. 

    """
    flow_from_time_points = [
            [7,0], [9, 8], [11.2, 11.4], [14.7, 24.1], [18.2, 39.0], [22.4, 51.7],
            [28.7, 66.6], [35.7, 75.2], [39.9, 80.6], [42.7, 83.7], [67.2, 100]
        ]
    FULL_RANGE_S = 70
    MAIN_LOOP_SLEEP_S = 2

    def __init__(self, name: str, services: ScadaInterface):
        super().__init__(name, services)
        self.keep_seconds: float = self.FULL_RANGE_S
        self.target_seconds_for_leaving_defrost: Optional[float] = None # 
        self._stop_requested = False
        self.target_temp_too_low: bool = False
        self.resetting = False
        self._movement_task = None # Track the current movement task
        self.move_start_s: float = 0
        self.idu_w_readings = deque(maxlen=15)
        self.odu_w_readings = deque(maxlen=15)
        self.hp_model = self.settings.hp_model
        self.latest_move_duration_s: float = 0
        # Define transitions with callback
        self.control_transitions = [
            {"trigger": "InitializationComplete", "source": "Initializing", "dest": "Dormant"},
            {"trigger": "HpTurnsOff", "source": "*", "dest": "MovingToFullSend"},
            {"trigger": "Blind", "source": "*", "dest": "MovingToFullSend"},
            {"trigger": "ReachFullSend", "source": "MovingToFullSend", "dest":"Dormant"},
            {"trigger": "HpPreparing", "source": "Dormant", "dest": "MovingToStartupHover"},
            {"trigger": "HpPreparing", "source": "MovingToFullSend", "dest": "MovingToStartupHover"},
            {"trigger": "ReachT2", "source": "MovingToStartupHover", "dest": "StartupHover"},
            {"trigger": "LeaveStartupHover", "source": "StartupHover", "dest": "PID"},
            {"trigger": "DefrostDetected", "source": "PID", "dest": "Defrost"},
            {"trigger": "LeavingDefrostDetected", "source": "Defrost", "dest": "PID"},
             
        ]
        self.transitions = [
            {"trigger": "StartKeepingMore", "source": "FullySend", "dest": "KeepingMore", "before": "before_keeping_more"},
            {"trigger": "StartKeepingMore", "source": "SteadyBlend", "dest": "KeepingMore", "before": "before_keeping_more"},
            {"trigger": "StartKeepingMore", "source": "KeepingLess", "dest": "KeepingMore", "before": "before_keeping_more"},
            {"trigger": "StartKeepingMore", "source": "KeepingMore", "dest": "KeepingMore", "before": "before_keeping_more"},
            {"trigger": "StopKeepingMore", "source": "KeepingMore", "dest": "SteadyBlend", "before": "before_keeping_steady"},
            {"trigger": "StartKeepingLess", "source": "FullyKeep", "dest": "KeepingLess", "before": "before_keeping_less"},
            {"trigger": "StartKeepingLess", "source": "SteadyBlend", "dest": "KeepingLess", "before": "before_keeping_less"},
            {"trigger": "StartKeepingLess", "source": "KeepingMore", "dest": "KeepingLess", "before": "before_keeping_less"},
            {"trigger": "StartKeepingLess", "source": "KeepingLess", "dest": "KeepingLess", "before": "before_keeping_less"},
            {"trigger": "StopKeepingLess", "source": "KeepingLess", "dest": "SteadyBlend", "before": "before_keeping_steady"},
            {"trigger": "ResetToFullySend", "source": "KeepingLess", "dest": "FullySend", "before": "before_keeping_steady"},
            {"trigger": "ResetToFullyKeep", "source": "KeepingMore", "dest": "FullyKeep", "before": "before_keeping_steady"},
        ]
        self.control_machine = Machine(
            model=self,
            states=SiegControlState.values(),
            transitions=self.control_transitions,
            initial=SiegControlState.Initializing,
            model_attribute="control_state",
            send_event=True,
        )
        self.control_state: SiegControlState = SiegControlState.Initializing
        self.machine = Machine(
            model=self,
            states=SiegValveState.values(),
            transitions=self.transitions,
            initial=SiegValveState.FullyKeep,
            model_attribute="valve_state",
            send_event=True, # Enable event passing to callbacks
        )
        self.valve_state: SiegValveState = SiegValveState.FullyKeep
        self.actuators_ready: bool = False

        # Heat pump LWT control settings
        self.target_lwt_from_boss: Optional[float] = None
        self.hp_boss_state = HpBossState.HpOn
        self.hp_start_s: float = time.time() # Track time since

        # Control parameters using time percent keep
        self.ultimate_gain = 1.0  # Ku
        self.ultimate_gain_seconds = 230 # Tu
        # Applying Ziegler-Nichols with 
        self.pid_sensitivity = 2
        self.proportional_gain = .4 * self.pid_sensitivity #  P = 0.2*Ku
        self.derivative_gain = 15 * self.pid_sensitivity # D = 0.33 * P * Tu
        self.integral_gain = 0.00017 * self.pid_sensitivity #  I =  0.1 × P ÷ Tu
        self.t1 = 7 # seconds where some flow starts going through the Sieg Loop
        self.t2 = 67 # seconds where all flow starts going through the Sieg Loop
        self.moving_to_calculated_target = False
        self.control_interval_seconds = 30

        self.lwt_readings = deque(maxlen=40)
        if self.flow_from_time_points[0][1] != 0:
            raise Exception(f"First flow point should be [x,0]!")
        if self.flow_from_time_points[-1][1] != 100:
            raise Exception(f"Last flow point should be [x,100]!")
        self.log(f"Starting with keep seconds at {round(self.keep_seconds,1)} s")

    def start(self) -> None:
        """ Required method. """
        self.services.add_task(
                asyncio.create_task(self.main(), name="Sieg Loop Synchronous Report")
            )

    def stop(self) -> None:
        """ Required method, used for stopping tasks. Noop"""
        self._stop_requested = True

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""
        ...

    ##############################################
    # Managing the target temperature
    ##############################################

    @property
    def target_lwt(self) -> float:
        """Returns target from boss if it exists. Otherwise
        returns default target which comes from the top of whatever
        tank is getting filled (store or buffer)"""
        if self.target_lwt_from_boss is not None:
            return self.target_lwt_from_boss
        return self.default_target_lwt()
    
    def default_target_lwt(self) -> float:
        """ Returns top depth of whatever tank is getting filled (store or buffer).
        If that does not exist, it reverts to 130F
        """
        if self.charge_discharge_relay_state == StoreFlowRelay.DischargingStore:
            t = self.hottest_buffer_temp_f()
        else:
            t = self.hottest_store_temp_f()
        if t is None:
            t = 130
        return t

    ##############################################
    # Control loop mechanics
    ##############################################

    def time_to_leave_startup_hover(self) -> bool:
        """ Yes if the time it would take to move to roughly the correct valve position
        is about how long it will take for the temperature to be at target given the current
        rate of change of lwt"""

        # TODO: if ISO valve is open use buffer depth 3
        lift_f = self.lift_f()
        if lift_f is None:
            self.trigger_control_event(ControlEvent.Blind)
            return False
        target_flow_percent = self.calc_eq_flow_percent(lift_f + 3)
        lwt_f = self.lwt_f()
    
        if target_flow_percent is None or lwt_f is None:
            self.log("Blind! Unable to calculate when to leave hover")
            self.trigger_control_event(ControlEvent.Blind)
            return False
        
        target_keep_s = self.time_from_flow(target_flow_percent)
        # This is how long it will take to move
        time_to_move = self.keep_seconds - target_keep_s

        if not hasattr(self, 'lwt_slope'):
            raise Exception("Expects update_derivative_calcs to be run first!")
        slope = self.lwt_slope
        if slope <= 0:
            self.log(f"Rate of change for LWT: {round(slope * 60, 1)} °F/min")
            return False
        
        time_til_target_lwt =  (self.target_lwt - lwt_f) / slope

        # logging
        now = datetime.now()
        s = now.second % 10
        sieg_cold_f = self.anticipated_sieg_cold_f()
        if sieg_cold_f is not None:
            if s == 0:
                self.log(f"Rate of change for LWT: {round(slope * 60, 1)} °F/min, {round(slope,1)} °F/s")
                self.log(f"Using anticipated sieg {round(sieg_cold_f,1)}°F, target {self.target_lwt}°F")
                self.log(f"target flow percent: {round(target_flow_percent,1)}%")
                self.log(f"time to move: {round(time_to_move,1)}")
                self.log(f"time til target lwt, using slope: {round(time_til_target_lwt, 1)}")
                
                if self.lift_f:
                    self.log(f"Current lift: {round(lift_f)}°F")

       
        buffer_time = 3.0 # 3 second buffer
        if time_til_target_lwt - time_to_move < buffer_time:
            self.log(f"Rate of change for LWT: {round(slope * 60, 1)} °F/min ({round(slope,1)} °F/s)")
            self.log(f"Time until target: {round(time_til_target_lwt)}")
            self.log(f"Seconds to move valve: {round(time_to_move)}")
            if self.lift_f:
                self.log(f"Current lift: {round(lift_f)}°F")
            return True

        return False

    def calc_eq_flow_percent(self, 
            lift_f: Optional[float] = None) -> Optional[float]:
        """Calculate the theoretical equilibrium flow keep percentage to achieve target LWT,
         sieg_cold_temp_f and target_lwt. If lift is not given then it uses current lift.

         If the control state is StartupHover or Defrost, that means water is not flowing 
         past the sieg cold temperature sensor and the _anticipated_ sieg cold temperature
         is used.

         Let tsc be shorthand for sieg_cold_temp_f
         Using the formula: k = 1 - (lift/(target - tsc))

         If lift is not given, uses current lift
         If sieg_cold_f is not given, uses current sieg_cold_f

        where k is flow_fraction
         Returns None if temps are not available
         
         target = lift + ewt
         ewt = k*target + (1-k)*sieg_cold
         target = k(target-sieg_cold) + sieg_cold + lift
         k = 1 - lift/(target-sieg_cold)
         """
        if lift_f is None:
            lift_f = self.lift_f()
        if self.control_state in [SiegControlState.StartupHover, SiegControlState.Defrost]:
            tsc = self.anticipated_sieg_cold_f()
        else:
            tsc = self.sieg_cold_f()
        lift_f = self.lift_f()
        if lift_f is None or tsc is None:
            self.log("Missing temp readings for equilibrium calc")
            return None

        # Avoid division by zero or negative values
        temp_diff = self.target_lwt - tsc
        if temp_diff <= 0:
            self.log(f"Target LWT {self.target_lwt}°F is lower than anticipated Sieg cold temp {tsc}°F")
            return 0 

        k = 1 - (lift_f / temp_diff)
        eq_flow_percent = max(0, min(k, 1)) * 100
        # if sieg_cold_f != self.sieg_cold_temp_f:
        #     self.log(f"Using sieg cold of {round(sieg_cold_f,1)}°F instead of actual {round(sieg_cold_f, 1)}°F")
        # self.log(f"Calculated target flow: {round(eq_flow_percent, 1)}% keep")
        # self.log(f"  Target LWT: {round(self.target_lwt, 1)}°F, Sieg Cold  {round(sieg_cold_f, 1)}°F")
        # self.log(f"  temp diff: {round(temp_diff, 1)}°F")
        # self.log(f"  lift: {round(lift_f, 1)}°F")
        # self.log(f"  lift/temp_diff: {round(lift_f/temp_diff,1)}")
        # self.log(f"  1 - lift/temp_diff: {round(k, 2)}")
        
        return eq_flow_percent

    def calc_flow_sensitivity(self) -> Optional[float]:
        """ calculate dLWT/d%k at the current operating point
        
        The sensitivity follows the formula dLWT/d%k = -Lift/(1-%k)^2

        Returns:
            Temperature change (°F) per percentage point change in flow keep
        """
        # if self.lift_f is None:
        #     return None
            
        # # Convert flow_percent_keep to fraction
        # k = self.flow_percent_keep / 100
        
        # # Avoid division by zero or very small denominators
        # if k >= 0.95:
        #     return 10  # Very high sensitivity
            
        # # Calculate the sensitivity using the formula
        # # Note: we divide by 100 to get sensitivity per percentage point rather than per fraction
        # sensitivity = self.lift_f / ((1 - k) ** 2) / 100
        
        # return sensitivity
        return 1

    def check_target_temp(self) -> None:
        """ Returns true if current target water temp is too low to hit.

        Only call this in the PID control state"""

        if self.control_state != SiegControlState.PID:
            raise Exception(f"target_too_low only ")
        tsc = self.sieg_cold_f(); lift = self.lift_f()
        if tsc is None or lift is None:
            self.trigger_control_event(ControlEvent.Blind)
            return
        if tsc + lift > self.target_lwt:
            if self.target_temp_too_low is False:
                self._send_to(self.primary_scada,
                              SiegTargetTooLow(
                                  FromGNodeAlias=self.layout.scada_g_node_alias,
                                  TargetLwtFx10=round(self.target_lwt * 10),
                                  SiegColdFx10=round(tsc * 10),
                                  HeatPumpDeltaTx10=round(lift*10),
                                  TimeMs=int(time.time() * 1000)
                              ))
                self.log(f"Target temperature is too low! sieg cold: {round(tsc,1)}, lift: {round(lift,1)}, target: {self.target_lwt}")
                self.target_temp_too_low = True
        else:
            if self.target_temp_too_low is True:
                self.target_temp_too_low = False
                self.log(f"Should now be able to hit target temp! sieg cold: {round(tsc,1)}, lift: {round(lift,1)}, target: {self.target_lwt}")

    def update_derivative_calcs(self) -> None:
        """Calculated self.lwt_slope - the rate of change of leaving water temperature (deg f per second)"
        """
        lwt_f = self.lwt_f()
        if lwt_f is None:
            self.log("Not updating lwt derivative calcs ... blind!")
            return
        current_time = time.time()
        self.lwt_readings.append((current_time, lwt_f))

        if len(self.lwt_readings) == 1:
            self.lwt_slope = 0
            return
        
        # Find the oldest reading that's at least 10 seconds old
        reference_time: Optional[float] = None
        reference_temp: Optional[float] = None
        min_time_difference = 10.0  # Minimum 10 seconds between readings

        # Iterate backwards (newest to oldest)
        for timestamp, temp in reversed(list(self.lwt_readings)[:-1]):  # Skip the current reading
            if current_time - timestamp >= min_time_difference:
                reference_time = timestamp
                reference_temp = temp
                break
                
        # If we don't have an old enough reading, use the oldest one we have
        if reference_time is None:
            reference_time, reference_temp = self.lwt_readings[0]
        if reference_temp is None or reference_time is None:
            raise Exception("reference_temp shoudl exist now")
        time_delta = current_time - reference_time
        temp_delta = lwt_f - reference_temp
        
        self.lwt_slope = temp_delta / time_delta
        #self.log(f"LWT slope: {round(self.lwt_slope * 60, 2)} °F/min over {round(time_delta, 1)} seconds")

    def calculate_delta_seconds(self, seconds_hack: bool = False) -> Optional[float]:
        """Calculate delta seconds for the next PID control interval, using
        ratio of flow as the independent variable. If seconds_hack is true, use
        the keep_seconds as the independant variable
        
        Returns None if blind
        """

        if self.control_state not in [SiegControlState.StartupHover, SiegControlState.PID]:
            raise Exception(f"Should not be running control loop in state {self.control_state}")

        lwt_f = self.lwt_f()
        lift_f = self.lift_f
        # 1. If we don't have visibility, trigger "Blind" which will go to FullSend
        if lift_f is None or lwt_f is None:
            return None
        
        # 2. Calculate error
        err = self.target_lwt - lwt_f
        
        # 3. Calculate PID terms
        # Proportional term
        proportional_term = self.proportional_gain * err
        
        # Derivative term (rate of change of error)
        # Store time and error for derivative calculation
        current_time = time.time()
        if len(self.lwt_readings) <= 1:
            error_delta = 0
            time_delta_s = 1
        else:
            last_lwt_time, last_lwt_f = self.lwt_readings[-2]
            if current_time - last_lwt_time < 20:
                error_delta = 0
                time_delta_s = 1
                self.log(f"That's strange, last_lwt_time is {round(current_time - last_lwt_time)} seconds ago!")
            else:
                last_error = self.target_lwt - last_lwt_f
                time_delta_s = current_time - last_lwt_time
                error_delta = err - last_error

        derivative_term = self.derivative_gain * (error_delta / time_delta_s)

        # Integral term
        if not hasattr(self, 'error_integral'):
            self.error_integral = 0

        # Add current error to integral, with anti-windup protection
        max_integral = 50  # Limit integral windup
        self.error_integral += err * self.control_interval_seconds
        self.error_integral = max(-max_integral, min(self.error_integral, max_integral))
        
        integral_term = self.integral_gain * self.error_integral

        self.log(f"PID adjustment:")
        self.log(f"  Error: {round(err, 1)}°F")
        # 4. Calculate total flow adjustment
        if seconds_hack:
            self.log(f"  P: {round(proportional_term, 1)} s, I: {round(integral_term, 1)} s,  D: {round(derivative_term, 1)} s")
            delta_s = proportional_term + integral_term + derivative_term
        else:
            flow_percent_adjustment = proportional_term + integral_term + derivative_term
            self.log(f"  P: {round(proportional_term, 1)}% flow, I: {round(integral_term, 1)}% flow,  D: {round(derivative_term, 1)}% flow")
            # Consider adjusting the PID using modeling of an expected rate of
            # change of the leaving water temperature as a function of flow percent
            #sensitivity = self.calc_flow_sensitivity()
            # if use_sensitivity:
            #     self.log(f"Sensitivity {round(sensitivity, 2)}.")
            #     flow_percent_adjustment = orig_adjustment/sensitivity

            # else:
            #    flow_percent_adjustment = orig_adjustment
            
            # Convert to time_percent_keep
            target_flow_percent = self.flow_percent_keep + flow_percent_adjustment
            target_time_s = self.time_from_flow(target_flow_percent)
            delta_s = target_time_s - self.keep_seconds
            self.log(f"  Flow target: {round(flow_percent_adjustment + self.flow_percent_keep,1)}%")
            self.log(f"  Flow adjustment: {round(flow_percent_adjustment,1)}%")

        # 6. Bound the adjustment to the physical limits of the valve
        if delta_s > 0:
            bounded_adjustment = min(delta_s, self.control_interval_seconds)
        else:
            bounded_adjustment = max(delta_s, -self.control_interval_seconds)
        
        self.log(f"  Time adjustment: {round(delta_s,1)} seconds")
        self.log(f"  Bounded time adjustment: {round(bounded_adjustment,1)} seconds")

        return bounded_adjustment

    async def leave_startup_hover(self) -> None:
        """ Move to the estimated valve position for hitting 
        target temp with 5 degrees of lift"""
        if self.lift_f is None:
            raise Exception("should not be blind here")
        lift_f = self.lift_f + 3
        
        self.moving_to_calculated_target = True
        sieg_cold_f = self.store_cold_pipe_f
        if sieg_cold_f is None:
            sieg_cold_f = self.anticipated_sieg_cold_f
        flow_target_percent = self.calc_eq_flow_percent(lift_f=lift_f, sieg_cold_f=sieg_cold_f)
        if flow_target_percent is None:
            raise Exception(f"Should not get here if blind")
        self.log(f"flow_target_percent is {round(flow_target_percent)}")
        keep_seconds_target = self.time_from_flow(flow_target_percent)
        self.log(f"Calculated target time: {round(keep_seconds_target,1)}% keep")
        delta_s = keep_seconds_target - self.keep_seconds
        await self._prepare_new_movement_task(delta_s)
        # and now wait another 25 seconds to settle down trigger_control_event(ControlEvent.ReachFullSend)
        self.log(f"Waiting 1 minute to see how this level works")
        await asyncio.sleep(delta_s + 60)
        self.moving_to_calculated_target = False

    async def leave_defrost(self) -> None:
        """ Go back to the target seconds set when we entered defrost"""
        self.moving_to_calculated_target = True
        if self.target_seconds_for_leaving_defrost is None:
            delta_s = self.keep_seconds
        else:
            delta_s = self.target_seconds_for_leaving_defrost - self.keep_seconds
            self.log(f"Moving back to {round(self.target_seconds_for_leaving_defrost,1)} seconds")
        asyncio.create_task(self._prepare_new_movement_task(delta_s))
        # wait another minute before going back into PID adjustments
        await asyncio.sleep(delta_s + 60)
        self.moving_to_calculated_target = False

    async def run_pid(self) -> None:
        """Check current temperatures and adjust valve position if needed. Only
        used when control state is PID"""

        #TODO think through safety to make sure it doesn't stay in 100% keep
        # if temps go away

        lwt_f = self.lwt_f(); lift_f = self.lift_f()
        if lwt_f is None or lift_f is None:
            self.log("Missing temperature readings, Blind ... aborting!")
            self.trigger_control_event(ControlEvent.Blind)
            return

        self.log(f"LWT {round(lwt_f,1)} | Target {round(self.target_lwt,1)} | Lift {round(lift_f,1)}")
        # Calculate target percent
        delta_s = self.calculate_delta_seconds(seconds_hack=True)
        if delta_s is None:
            self.trigger_control_event(ControlEvent.Blind)
            return
        
        # Only move if significant change needed (avoid hunting)
        if abs(delta_s) >= 0.5:
            await self._prepare_new_movement_task(delta_s)


    ##############################################
    # State machine mechanics
    ##############################################

    def on_enter_moving_to_keep(self, event):
        """Called when entering the MovingToStartupHover state"""
        self.log(f"Moving to keep position (t2: {self.t2}%) to prepare for heat pump start")
        if self.hp_model == HpModel.LgHighTempHydroKitPlusMultiV:
            self._send_to(
                self.hp_boss,
                SiegLoopReady()
            )
        else:
            raise Exception("Think through how Sieg Loop works for Samsung")
        self.hp_start_s = time.time()
        # Create a new task for the movement to t2
        delta_s = self.t2 - self.keep_seconds
        asyncio.create_task(self._prepare_new_movement_task(delta_s))

    def on_enter_startup_hover(self, event):
        """Called when entering the Hover state"""
        self.log(f"Hovering at t2 position ({self.t2}%) waiting for heat pump to establish flow")

        if self.hp_model in [HpModel.SamsungFiveTonneHydroKit, HpModel.SamsungFourTonneHydroKit]:
            self._send_to(
                self.hp_boss,
                SiegLoopReady()
            )

        # Create a task to monitor for when to leave startup hover
        self._startup_hover_monitor_task = asyncio.create_task(
            self._monitor_startup_hover(), 
            name="startup_hover_monitor"
        )

    def on_enter_dormant(self, event):
        """Called when entering the Dormant state"""
        self.log("Heat pump off, entering dormant state")

    def on_enter_moving_to_full_send(self, event):
        self.log(f"Moving to full send")
        asyncio.create_task(self._prepare_new_movement_task(-self.keep_seconds - 10))

    def on_enter_defrost(self, event) -> None:
        """ Set the target seconds for leaving defrost and then move to full keep.
        
        Since keep_seconds is an inaccurate integration that gets off as we do
        the PID, use the percent flow as measured from the Siegenthaler and primary
        flow meter. 
        
        """
        flow_percent = self.get_current_flow_percent()
        if flow_percent is None:
            self.target_seconds_for_leaving_defrost = self.keep_seconds
        else:
            self.target_seconds_for_leaving_defrost = self.time_from_flow(flow_percent)

        self.log(f"Setting target seconds for leaving defrost to {round(self.target_seconds_for_leaving_defrost,1)}")
        nominal_delta_s = self.FULL_RANGE_S - self.target_seconds_for_leaving_defrost

        # Go 15 seconds more for good measure
        asyncio.create_task(self._prepare_new_movement_task(nominal_delta_s + 15))


    def trigger_control_event(self, event: ControlEvent) -> None:
        now_ms = int(time.time() * 1000)
        orig_state = self.control_state

        if self.resetting:
            raise Exception("Do not interrupt resetting to fully send or fully keep!")

        # Trigger the state machine transition
        if event == ControlEvent.Blind:
            self.Blind()
        elif event == ControlEvent.DefrostDetected:
            self.DefrostDetected()
        elif event == ControlEvent.InitializationComplete:
            self.InitializationComplete()
        elif event == ControlEvent.HpTurnsOff:
            self.HpTurnsOff()
        elif event == ControlEvent.HpPreparing:
            self.HpPreparing()
        elif event == ControlEvent.LeavingDefrostDetected:
            self.LeavingDefrostDetected()
        elif event == ControlEvent.LeaveStartupHover:
            self.LeaveStartupHover()
        elif event == ControlEvent.ReachT2:
            self.ReachT2()
        elif event == ControlEvent.ReachFullSend:
            self.ReachFullSend()
        else:
            raise Exception(f"Unknown control event {event}")

        self.log(f"{event}: {orig_state} -> {self.control_state}")

        # If we're leaving StartupHover state, cancel the monitor task
        if orig_state == SiegControlState.StartupHover and self.control_state != SiegControlState.StartupHover:
            if hasattr(self, '_startup_hover_monitor_task') and self._startup_hover_monitor_task is not None:
                if not self._startup_hover_monitor_task.done():
                    self._startup_hover_monitor_task.cancel()
                self._startup_hover_monitor_task = None

        # Manually call the appropriate callback based on the new state
        if self.control_state == SiegControlState.MovingToStartupHover and orig_state != SiegControlState.MovingToStartupHover:
            self.on_enter_moving_to_keep(event)
        elif self.control_state == SiegControlState.StartupHover and orig_state != SiegControlState.StartupHover:
            self.on_enter_startup_hover(event)
        elif self.control_state == SiegControlState.PID and orig_state == SiegControlState.StartupHover:
            asyncio.create_task(self.leave_startup_hover())
        elif self.control_state == SiegControlState.PID and orig_state == SiegControlState.Defrost:
            asyncio.create_task(self.leave_defrost())
        elif self.control_state == SiegControlState.Dormant and orig_state != SiegControlState.Dormant:
            self.on_enter_dormant(event)
        elif self.control_state == SiegControlState.MovingToFullSend and orig_state != SiegControlState.MovingToFullSend:
            self.on_enter_moving_to_full_send(event)
        elif self.control_state == SiegControlState.Defrost:
            self.on_enter_defrost(event)


        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=SiegControlState.enum_name(),
                State=self.control_state,
                UnixMs=now_ms,
                Cause=event
            )
        )

    ##############################################
    # Valve State Machine
    ##############################################

    def before_keeping_more(self, event):
        self.change_to_hp_keep_more()
        self.sieg_valve_active()
        self.move_start_s = time.time()

    def before_keeping_less(self, event):
        self.change_to_hp_keep_less()
        self.sieg_valve_active()
        self.move_start_s = time.time()

    def before_keeping_steady(self, event):
        # Logic for steady blend state (including FullySend and FullyKeep)
        self.sieg_valve_dormant()
        self.latest_move_duration_s = time.time() - self.move_start_s

    def trigger_valve_event(self, event: ValveEvent) -> None:
        now_ms = int(time.time() * 1000)
        orig_state = self.valve_state

        if self.resetting:
            raise Exception("Do not interrupt resetting to fully send or fully keep!")

        # Trigger the state machine transition
        if event == ValveEvent.StartKeepingMore:
            self.StartKeepingMore()
        elif event == ValveEvent.StartKeepingLess:
            self.StartKeepingLess()
        elif event == ValveEvent.StopKeepingMore:
            self.StopKeepingMore()
        elif event == ValveEvent.StopKeepingLess:
            self.StopKeepingLess()
        elif event == ValveEvent.ResetToFullySend:
            self.ResetToFullySend()
        elif event == ValveEvent.ResetToFullyKeep:
            self.ResetToFullyKeep()
        else:
            raise Exception(f"Unknown valve event {event}")

        self.log(f"{event}: {orig_state} -> {self.valve_state}")

        # TODO: add a new node for the valve; sieg-loop will be control state
        # self._send_to(
        #     self.primary_scada,
        #     SingleMachineState(
        #         MachineHandle=self.node.handle,
        #         StateEnum=SiegValveState.enum_name(),
        #         State=self.valve_state,
        #         UnixMs=now_ms,
        #         Cause=event
        #     )
        # )

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        from_node = self.layout.node(message.Header.Src, None)
        if from_node is None:
            return Ok(False)
        payload = message.Payload
        match payload:
            case ActuatorsReady():
                try:
                    self.process_actuators_ready(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_actuators_ready")
            case AnalogDispatch():
                try:
                    asyncio.create_task(self.process_analog_dispatch(from_node, payload), name="analog_dispatch")
                except Exception as e:
                    self.log(f"Trouble with process_analog_dispatch: {e}")
            case FsmFullReport():
                ... # got report back from relays
            case ResetHpKeepValue():
                try:
                    self.process_reset_hp_keep_value(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_reset_hp_keep_value: {e}")
            case SetLwtControlParams():
                try:
                    self.process_set_lwt_control_params(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_lwt_control_paramst: {e}")
            case SetTargetLwt():
                try:
                    self.process_set_target_lwt(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_set_target_lwt: {e}")
            case SingleMachineState():
                self.process_single_machine_state(from_node, payload)
            case _: 
                self.log(f"{self.name} received unexpected message: {message.Header}"
            )
        return Ok(True)

    def process_actuators_ready(self, from_node: ShNode, payload: ActuatorsReady) -> None:
        """Move to full send on startup"""
        self.actuators_ready = True
        asyncio.create_task(self.initialize())
        self.log(f"Actuators ready")

    async def initialize(self) -> None:
        if not self.actuators_ready:
            raise Exception("Call AFTER actuators ready")
        self.log("Initializing Sieg valve to FullySend position")
        await self._prepare_new_movement_task(-self.FULL_RANGE_S)

        # Let movement complete
        await asyncio.sleep(self.FULL_RANGE_S)

        self.log("Waiting another 5 seconds")
        await asyncio.sleep(5)
        # InitializationComplete: Initializing -> Dormant
        if self.control_state == SiegControlState.Initializing:
            self.trigger_control_event(ControlEvent.InitializationComplete)
        if self.hp_boss_state in [HpBossState.PreparingToTurnOn, HpBossState.HpOn]:
            # HpPreparing: Dormant -> MovingToStartupHover
            self.trigger_control_event(ControlEvent.HpPreparing)

    async def process_analog_dispatch(self, from_node: ShNode, payload: AnalogDispatch) -> None:    
        # TODO: fix this later
        # if from_node != self.boss:
        #     self.log(f"sieg loop expects commands from its boss {self.boss.Handle}, not {from_node.Handle}")
        #     return

        # if self.boss.handle != payload.FromHandle:
        #     self.log(f"boss's handle {self.boss.handle} does not match payload FromHandle {payload.FromHandle}")
        #     return

        target_s = payload.Value
        self.log(f"Received command to set valve to {target_s} seconds")
        delta_s = target_s - self.keep_seconds
        # move to target percent
        asyncio.create_task(self._prepare_new_movement_task(delta_s))

    def process_reset_hp_keep_value(
        self, from_node: ShNode, payload: ResetHpKeepValue
    ) -> None:
        self.log(f"Got ResetHpKeepValue")
        if from_node != self.boss:
            self.log(f"sieg loop expects commands from its boss {self.boss.Handle}, not {from_node.Handle}")
            return

        if self.boss.handle != payload.FromHandle:
            self.log(f"boss's handle {self.boss.handle} does not match payload FromHandle {payload.FromHandle}")
            return
        
        if self._movement_task:
            self.send_glitch(f"Not resetting hp keep value while moving")
            return
        self.log(f"Resetting percent keep from {self.keep_seconds} to {payload.HpKeepSecondsTimes10 / 10} without moving valve")
        self.keep_seconds = payload.HpKeepSecondsTimes10 / 10
        self._send_to(
            self.primary_scada,
            SingleReading(
                ChannelName=H0CN.hp_keep_seconds_x_10,
                Value=round(self.keep_seconds * 10),
                ScadaReadTimeUnixMs=int(time.time() *1000)
            )
        )

    def process_set_lwt_control_params(self, from_node: ShNode, payload: SetLwtControlParams) -> None:
        # consider adding to HW Layou?
        if payload.ToHandle != self.node.handle:
            self.log(f"Ignoring LwtControlParams with ToHandle {payload.ToHandle} != {self.node.handle}")
            return
        self.proportional_gain = payload.ProportionalGain
        self.derivative_gain = payload.DerivativeGain
        self.integral_gain = payload.IntegralGain
        self.control_interval_seconds = payload.ControlIntervalSeconds
        self.t1 = payload.T1
        self.t2 = payload.T2
        self.log(f"Using {payload}")

    def process_single_machine_state(self, from_node: ShNode, payload: SingleMachineState) -> None:
        self.latest = payload
        self.log(f"JUST GOT {payload.State} from HpBoss")
        if payload.StateEnum != HpBossState.enum_name():
            raise Exception(f"Not expecting {payload}")
        if from_node != self.hp_boss:
            raise Exception("Not expecting sms except from HpBoss")
        self.hp_boss_state = payload.State
        if self.control_state == SiegControlState.Initializing:
            self.log(f"IGNORING Hp State {payload.State} until done initializing")
            return

        if payload.State == HpBossState.HpOff:
            if self.control_state not in [SiegControlState.Dormant, SiegControlState.MovingToFullSend]:
                self.trigger_control_event(ControlEvent.HpTurnsOff)
        elif payload.State == HpBossState.PreparingToTurnOn:
            if self.control_state not in [SiegControlState.Dormant, SiegControlState.MovingToFullSend]:
                self.log(f"That's strange! Got PreparingToTurnOn when control state is {self.control_state}")
            else:
                if self.is_blind():
                    self.log(f"NOT entering control loop: EWT: {self.ewt_f()} LWT: {self.lwt_f()}")
                else:
                    self.trigger_control_event(ControlEvent.HpPreparing)
        elif payload.State == HpBossState.HpOn:
            self.hp_start_s = time.time()

    def process_set_target_lwt(self, from_node: ShNode, payload: SetTargetLwt) -> None:
        if from_node.Handle != payload.FromHandle:
            raise Exception(f"from_node handle {from_node.Handle} does not match payload {payload.FromHandle}")
        self.target_lwt_from_boss = payload.TargetLwtF
        self.log(f"Boss just set target lwt to {self.target_lwt}")

    async def clean_up_old_task(self) -> None:
        if hasattr(self, '_movement_task') and self._movement_task and not self._movement_task.done():
            self.log(f"Cancelling movement task {self._current_task_id}")
            self._movement_task.cancel()
            
            # Wait for the task to actually complete
            try:
                # Use a timeout to avoid waiting forever if something goes wrong
                await asyncio.wait_for(self._movement_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                self.log("Cancelled previous task")
            
            # Ensure proper state cleanup regardless of how the task ended
            if self.valve_state == SiegValveState.KeepingMore:
                self.trigger_valve_event(ValveEvent.StopKeepingMore)
                self.log(f"Triggered StopKeepingMore after cancellation")
            elif self.valve_state == SiegValveState.KeepingLess:
                self.trigger_valve_event(ValveEvent.StopKeepingLess)
                self.log(f"Triggered StopKeepingLess after cancellation")

            # Set task to None after cancellation
            self._movement_task = None

    def complete_move(self, task_id: str) -> None:
        if self.valve_state == SiegValveState.KeepingMore:
            # Allowing keep_seconds more than FULL_RANGE_SECONDS
            #if self.keep_seconds == self.FULL_RANGE_S:
            #     self.trigger_valve_event(ValveEvent.ResetToFullyKeep)
            # else:
            self.trigger_valve_event(ValveEvent.StopKeepingMore)
        elif self.valve_state == SiegValveState.KeepingLess:
            # Allowing keep_seconds less than 0
            # if self.keep_seconds == 0:
            #     self.trigger_valve_event(ValveEvent.ResetToFullySend)
            # else:
            self.trigger_valve_event(ValveEvent.StopKeepingLess)
        self.log(f"Movement {task_id} completed: {round(self.keep_seconds, 1)} seconds, state {self.valve_state}")


    async def _monitor_startup_hover(self) -> None:
        """Monitor LWT and other conditions to determine when to leave startup hover state"""
        try:
            while self.control_state == SiegControlState.StartupHover:
                # Update derivative calculations
                self.update_derivative_calcs()
                
                # Check if it's time to leave startup hover
                if self.time_to_leave_startup_hover():
                    self.log("Leaving startup hover based on LWT rate of change")
                    self.trigger_control_event(ControlEvent.LeaveStartupHover)
                    asyncio.create_task(self.leave_startup_hover())
                    break
                
                # Check every second
                await asyncio.sleep(1.0)
        
        except asyncio.CancelledError:
            self.log("Startup hover monitoring cancelled")
            raise
        except Exception as e:
            self.log(f"Error in startup hover monitoring: {e}")
            # Don't let exceptions in the monitor task break the system
        finally:
            self.log("Startup hover monitoring complete")

    async def _prepare_new_movement_task(self, delta_s: float) -> str:
        """Create a new movement task with proper cleanup of existing tasks.
        
        Args:
            time_target_percent: The target valve position percentage, as a percentage
            of time moving from one end of its range to the other
            
        Returns:
            task_id: The ID of the new task
        """
        
        # Cancel any existing movement task
        await self.clean_up_old_task()
        
        # Generate a new task ID for this movement
        new_task_id = str(uuid.uuid4())[-4:]
        self._current_task_id = new_task_id

        if delta_s > 0:
            self.log(f"Task {new_task_id}: move to keep for {round(delta_s,1)} seconds")
        else:
            self.log(f"Task {new_task_id}: move to send for {round(-delta_s,1)} seconds")

        # Create a new task for the movement
        self._movement_task = asyncio.create_task(
            self._adjust_keep_seconds(delta_s, new_task_id)
        )
        
        return new_task_id
    
    async def _adjust_keep_seconds(self, delta_s: float, task_id: str) -> None:
        """Move the valve by delta_s seconds."""

        target_seconds = self.keep_seconds + delta_s
        if  delta_s == 0:
            self.log(f"Already at target {round(delta_s,1)} s")
            # Check if we need to trigger ReachT2 event
            if self.control_state == SiegControlState.MovingToStartupHover and target_seconds == self.t2:
                self.trigger_control_event(ControlEvent.ReachT2)
            return
            
        # Determine direction
        moving_to_more_keep = 0 < delta_s
        

        # Wait a moment to ensure the state machine has settled
        await asyncio.sleep(0.2)
        # Set the appropriate state
        try:
            if moving_to_more_keep:
                self.trigger_valve_event(ValveEvent.StartKeepingMore)
                # Now process the movement in a loop
                delta_so_far = 0
                while delta_so_far < delta_s:
                    # Check if this task has been superseded
                    if task_id != self._current_task_id:
                        self.log(f"Task {task_id} has been superseded, stopping")
                        break
                    incremental_delta_s = min(1, delta_s - delta_so_far)
                    self.log(f"keep seconds {round(self.keep_seconds,1)}  [{task_id}]")
                    start_s = time.time()
                    await self._keep_more(start_s, task_id, incremental_delta_s)
                    delta_so_far += time.time() - start_s
                    # Allow for cancellation to be processed
                    await asyncio.sleep(0)
            else:
                self.trigger_valve_event(ValveEvent.StartKeepingLess)
                
                # Now process the movement in a loop
                delta_so_far = 0
                print(f"delta_so_far is {delta_so_far} and delta_s is {delta_s}")
                while delta_so_far > delta_s:
                    # Check if this task has been superseded
                    if task_id != self._current_task_id:
                        self.log(f"Task {task_id} has been superseded, stopping")
                        break
                        
                    incremental_delta_s = min(1, delta_so_far - delta_s)
                    self.log(f"keep seconds {round(self.keep_seconds,1)}  [{task_id}]")
                    start_s = time.time()
                    await self._keep_less(start_s, task_id, incremental_delta_s)
                    delta_so_far -= time.time() - start_s
                    # Allow for cancellation to be processed
                    await asyncio.sleep(0)

            # At the end of the method, after movement is complete:
            if task_id == self._current_task_id:
                # self.log(f"{round(self.time_percent_keep)} keep [{task_id} COMPLETED]")
                self.complete_move(task_id)
                
                # Check if we need to trigger ReachT2 event
                if self.control_state == SiegControlState.MovingToStartupHover and target_seconds >= self.t2:
                    self.trigger_control_event(ControlEvent.ReachT2)
                # Think about how if ever we want to recalibrate with "ReachFullSend"
                # elif self.control_state == SiegControlState.MovingToFullSend and delta_s == 0:
                #     self.trigger_control_event(ControlEvent.ReachFullSend)

        except asyncio.CancelledError:
            self.log(f"Movement cancelled at {self.keep_seconds} seconds from FullSend")
            # Let the cancellation propagate to the caller - don't set state here
            # as clean_up_old_task handles the FSM state transition
            raise
        
        except Exception as e:
            self.log(f"Error during movement: {e}")
            self.complete_move(task_id)

        finally:
            # Always set the task to None when complete, whether successful or not
            self._movement_task = None

    async def _keep_less(self, start_s: float, task_id: str, fraction: Optional[float] = None) -> None:
        """keep 1 second less, or fraction less (if fraction exists and is less than 1)"""
        # Check if we're still the current task
        if task_id != self._current_task_id:
            return
        if self.valve_state != SiegValveState.KeepingLess:
            raise Exception(f"Only call _keep_one_percent_less in state KeepingLess, not {self.valve_state}")
            
        sleep_s = 1
        if fraction:
            if fraction > 1:
                raise Exception("fraction needs to be less than 1")
            sleep_s = fraction
        orig_keep = self.keep_seconds
        
        await asyncio.sleep(sleep_s)
        now = time.time()
        delta_s = now - start_s
        # Check again if we're still the current task after sleeping
        if task_id != self._current_task_id:
            return
        
        self.keep_seconds = max(0, orig_keep - delta_s)
        self._send_to(
            self.primary_scada,
            SingleReading(
                ChannelName=H0CN.hp_keep_seconds_x_10,
                Value=round(self.keep_seconds * 10),
                ScadaReadTimeUnixMs=int(time.time() *1000)
            )
        )

    async def _keep_more(self, start_s: float, task_id: str, fraction: Optional[float] = None) -> None:
        """Or keep fraction percent more ... REQUIRES fraction to be less than 1"""
        # Check if we're still the current task
        if task_id != self._current_task_id:
            return
        if self.valve_state != SiegValveState.KeepingMore:
            raise Exception(f"Only call _keep_one_percent_more in state KeepingMore, not {self.valve_state}")
        sleep_s = 1
        if fraction:
            if fraction > 1:
                raise Exception("fraction needs to be less than 1")
            sleep_s = fraction

        orig_keep = self.keep_seconds
        await asyncio.sleep(sleep_s)
        now = time.time()
        delta_s = now - start_s
        # Check again if we're still the current task after sleeping
        if task_id != self._current_task_id:
            return
        
        self.keep_seconds = min(self.FULL_RANGE_S, orig_keep + delta_s)
        self._send_to(
            self.primary_scada,
            SingleReading(
                ChannelName=H0CN.hp_keep_seconds_x_10,
                Value=round(self.keep_seconds * 10),
                ScadaReadTimeUnixMs=int(time.time() *1000)
            )
        )

    async def keep_harder(self, seconds: int, task_id: str) -> None:
        try:
            if self.valve_state != SiegValveState.FullyKeep:
                self.log("Use only when in FullyKeep")
                return
            self.change_to_hp_keep_more()
            self.sieg_valve_active()
            self.send_glitch(f"[{task_id}] Keeping for {seconds} seconds more")
            await asyncio.sleep(seconds)
            # Check if this task has been superseded
            if task_id != self._current_task_id:
                self.log(f"Task {task_id} has been superseded!")
            else:
                self.sieg_valve_dormant()
                
        except asyncio.CancelledError:
            self.log(f"send_harder task cancelled")
            # Don't set valve to dormant - the cancelling code handles this
            raise
        except Exception as e:
            self.log(f"Error during keep_harder: {e}")
            self.sieg_valve_dormant()
            self.send_glitch(f"Error during keep_harder: {e}", LogLevel.Error)
        finally:
            # Always set the task to None when complete
            self._movement_task = None
            self.log(f"Task {task_id} complete")

    async def send_harder(self, seconds: int, task_id: str) -> None:
        try:
            if self.valve_state != SiegValveState.FullySend:
                self.log("Use when in FullySend")
                return
            self.change_to_hp_keep_less()
            self.sieg_valve_active()
            self.send_glitch(f"[{task_id}] Sending for {seconds} seconds more")
            await asyncio.sleep(seconds)
            # Check if this task has been superseded
            if task_id != self._current_task_id:
                self.log(f"Task {task_id} has been superseded!")
            else:
                self.sieg_valve_dormant()
        except asyncio.CancelledError:
            self.log(f"keep_harder task cancelled")
            # Don't set valve to dormant - the cancelling code handles this
            raise
        except Exception as e:
            self.log(f"Error during send_harder: {e}")
            self.sieg_valve_dormant()
            self.send_glitch(f"Error during send_harder: {e}", LogLevel.Error)
        finally:
            # Always set the task to None when complete
            self._movement_task = None
            self.log(f"Task {task_id} complete")

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, 400)]
    
    async def main(self):
        # This loop happens either every every second
        while not self._stop_requested:
            now = datetime.now()

            self.update_power_readings()
            if self.control_state == SiegControlState.PID:
                self.check_for_defrost()
            elif self.control_state == SiegControlState.Defrost:
                self.check_for_leaving_defrost()
            elif self.control_state == SiegControlState.StartupHover: 
                if self.time_to_leave_startup_hover():
                    self.trigger_control_event(ControlEvent.LeaveStartupHover)
            seconds_into_control_loop = now.second % self.control_interval_seconds
            milliseconds = now.microsecond / 1000
            if seconds_into_control_loop == 0 and milliseconds < 100:
                # We're at the top of a control interval (within 100ms)
                self.log(f"Moving to calculated target: {self.moving_to_calculated_target}")
                
                # Update derivative calculations
                self.update_derivative_calcs()
                if self.is_blind():
                    # Blind: * -> MovingToFullSend
                    self.trigger_control_event(ControlEvent.Blind)

                elif self.control_state == SiegControlState.PID:
                    self.check_target_temp()
                    # Consider adding additional control states
                    if not self.moving_to_calculated_target and not self.target_temp_too_low:
                        # Run temperature control without awaiting to avoid blocking
                        asyncio.create_task(self.run_pid())
                    else:
                        self.log("Not running PID loop ... still moving to calculated target")
        
            nap_time = self.MAIN_LOOP_SLEEP_S - (now.microsecond / 1_000_000)
            await asyncio.sleep(nap_time)

            # Report status periodically
            if now.second == 0 and now.minute % 5 == 0:
                self._send(PatInternalWatchdogMessage(src=self.name))
                self._send_to(
                self.primary_scada,
                    SingleReading(
                        ChannelName=H0CN.hp_keep_seconds_x_10,
                        Value=round(self.keep_seconds * 10),
                        ScadaReadTimeUnixMs=int(time.time() *1000)
                    )
                )
            
    def send_glitch(self, summary: str, log_level: LogLevel=LogLevel.Info) -> None:
        self._send_to(
                self.primary_scada,
                Glitch(
                    FromGNodeAlias=self.layout.scada_g_node_alias,
                    Node=self.node.Name,
                    Type=log_level,
                    Summary=summary,
                    Details=summary
                )
            )
        self.log(summary)

    def anticipated_sieg_cold_f(self) -> Optional[float]:
        """Returns the anticipated water temperature at the cold side of the mixing T into
        the siegenthaler loop. If the ISO valve is closed, it uses the coldest store tank
        temp. If the ISO valve is open, it uses the coldest buffer tank temp 

        If a tank temp sensor is none, revert to the (wired) sieg cold

        TODO: pay attention to distribution pump and do some mix of distribution rwt and
        coldest buffer tank temp, using flow meters to get the mix correct
        """
  
        if self.charge_discharge_relay_state() == StoreFlowRelay.DischargingStore:
            t = self.coldest_buffer_temp_f()
        else:
            t = self.coldest_store_temp_f()
        if t is None:
            t = self.sieg_cold_f()
        return t

    def seconds_since_hp_on(self) -> Optional[float]:
        if not (self.hp_boss_state == HpBossState.HpOn):
            return None
        else:
            return time.time() - self.hp_start_s

    def is_blind(self) -> bool:
        if self.lift_f() is None:
            return True
        return False

    ####################
    # Flow related
    ####################

    def get_current_flow_percent(self) -> Optional[float]:
        sieg = self.sieg_flow_gpm()
        primary = self.primary_flow_gpm()
        if sieg is None or primary is None:
            return None
        if primary == 0:
            return None
        return 100 * sieg / primary

    def flow_from_time(self, time_s: float) -> float:
        """Convert valve position in seconds (time_s,  seconds from valve 
        at its fully send stop endpoint)) to actual flow percentage 
        (flow_percent_keep)
        """
        # Time to flow points (experimental)
        points =  self.flow_from_time_points
        x = time_s
        # Below the first point
        if x <= points[0][0]:
            return 0

        # Above the last point
        if x >= points[-1][0]:
            return 100

        # Find the segment x lies within
        for i in range(1, len(points)):
            x0, y0 = points[i - 1]
            x1, y1 = points[i]
            if x0 <= x <= x1:
                y = (x - x0) * (y1 - y0) / (x1 - x0) + y0
                return y

        raise ValueError(f"Interpolation failed – {x} not in 0-100!")

    def time_from_flow(self, flow_percent_keep: float) -> float:
        """Convert actual flow percentage (flow_percent_keep) to valve position
        (seconds from valve at its fully send stop endpoint)
        """
        points = []
        for point in self.flow_from_time_points:
            points.append([point[1], point[0]])

        x = flow_percent_keep
        if not (0<=x and x<=100):
            old_x = x
            x = max(0, min(x, 100))
            self.log(f"changing flow percent keep from {old_x} to {x}")
        # Find the segment x lies within
        for i in range(1, len(points)):
            x0, y0 = points[i - 1]
            x1, y1 = points[i]
            if x0 <= x <= x1:
                y = (x - x0) * (y1 - y0) / (x1 - x0) + y0
                return y

        raise Exception(f"time_from_flow requires flow_percent_keep between 0 and 100")

    @property
    def flow_percent_keep(self) -> float:
        """Calculate the current flow percentage through the keep path based on valve position"""
        return self.flow_from_time(self.keep_seconds)

    ######################
    # Defrost related
    ######################

    def check_for_leaving_defrost(self) -> None:
        """ Determine when to go back to PID as defrost is finishing"""
        try: 
            good_readings = self.update_power_readings()
        except Exception as e:
            self.log(f"Trouble with update_power_readings: {e}")
        if good_readings:
            if self.control_state == SiegControlState.Defrost:
                if self.hp_model == HpModel.LgHighTempHydroKitPlusMultiV:
                    if self.lg_high_temp_hydrokit_leaving_defrost():
                        self.trigger_control_event(ControlEvent.LeavingDefrostDetected)
                        self.log("Leaving defrost detected")
                elif self.hp_model in [HpModel.SamsungFourTonneHydroKit,
                                    HpModel.SamsungFiveTonneHydroKit]:
                    if self.samsung_entering_defrost():
                        self.trigger_control_event(ControlEvent.LeavingDefrostDetected)
                        self.log("Defrost detected!")

    def lg_high_temp_hydrokit_leaving_defrost(self) -> bool:
        """
        LG is leaving defrost if lift is more than 4
        """
        lift_f = self.lift_f()
        if lift_f is None:
            return False
        if lift_f > 4:
            return True
        return False

    def samsung_leaving_defrost(self) -> bool:
        """
        Samsung is leaving defrost if lift is more than 4
        """
        lift_f = self.lift_f()
        if lift_f is None:
            return False
        if lift_f > 4:
            return True
        return False

    def check_for_defrost(self) -> None:
        """
        Responsible for helping to detect and triggering the defrost state change
        """

        try: 
            good_readings = self.update_power_readings()
        except Exception as e:
            self.log(f"Trouble with update_power_readings: {e}")
        if good_readings:
            if self.control_state == SiegControlState.PID:
                if self.hp_model == HpModel.LgHighTempHydroKitPlusMultiV:
                    if self.lg_high_temp_hydrokit_entering_defrost():
                        self.trigger_control_event(ControlEvent.DefrostDetected)
                        self.log("Defrost detected!")
                elif self.hp_model in [HpModel.SamsungFourTonneHydroKit,
                                    HpModel.SamsungFiveTonneHydroKit]:
                    if self.samsung_entering_defrost():
                        self.trigger_control_event(ControlEvent.DefrostDetected)
                        self.log("Defrost detected!")

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

    def update_power_readings(self) -> bool:
        odu_pwr = self.odu_pwr()
        idu_pwr = self.idu_pwr()
        if (odu_pwr is None) or (idu_pwr is None):
            return False 
        self.odu_w_readings.append(odu_pwr)
        self.idu_w_readings.append(idu_pwr)
        return True
