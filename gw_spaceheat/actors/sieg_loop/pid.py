import time
import uuid
import asyncio
from enum import auto
from collections import deque
from result import Ok, Result
from transitions import Machine
from typing import Any, Optional, Sequence

from scada_app_interface import ScadaAppInterface
from gwproto.message import Message
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import StoreFlowRelay
from gwsproto.named_types import FsmFullReport
from gwsproto.enums.gw_str_enum import GwStrEnum
from actors.hp_boss import SiegLoopReady
from gwsproto.enums.hp_boss_state import HpBossState
from actors.sh_node_actor import ShNodeActor
from gwsproto.named_types import ActuatorsReady, SetTargetLwt, SingleMachineState


class SiegValveState(GwStrEnum):
    KeepingMore = auto()
    KeepingLess = auto()
    SteadyBlend = auto()
    FullySend = auto()
    FullyKeep = auto() 

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "sieg.valve.state"


class SiegValveEvent(GwStrEnum):
    StartKeepingMore = auto()
    StartKeepingLess = auto()
    StopKeepingMore = auto()
    StopKeepingLess = auto()
    ResetToFullySend = auto()
    ResetToFullyKeep = auto()


class SiegControlState(GwStrEnum):
    StartupHover = auto()
    Pid = auto()
    HpOff = auto()

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.sieg.control.state"


class SiegControlEvent(GwStrEnum):
    HpTurnsOff = auto()
    HpTurnsOn = auto()
    LeaveStartupHover = auto()


class SiegLoopPid(ShNodeActor):
    FULL_RANGE_S = 100
    MAIN_LOOP_SLEEP_S = 2

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self._stop_requested = False

        # --------------------------------------
        # Valve state machine
        # --------------------------------------

        self.valve_transitions = [
            {"trigger": "StartKeepingMore", "source": "FullySend", "dest": "KeepingMore", "before": "before_keeping_more"},
            {"trigger": "StartKeepingMore", "source": "SteadyBlend", "dest": "KeepingMore", "before": "before_keeping_more"},
            {"trigger": "StartKeepingMore", "source": "KeepingLess", "dest": "KeepingMore", "before": "before_keeping_more"},
            {"trigger": "StartKeepingMore", "source": "KeepingMore", "dest": "KeepingMore", "before": "before_keeping_more"},

            {"trigger": "StartKeepingLess", "source": "FullyKeep", "dest": "KeepingLess", "before": "before_keeping_less"},
            {"trigger": "StartKeepingLess", "source": "SteadyBlend", "dest": "KeepingLess", "before": "before_keeping_less"},
            {"trigger": "StartKeepingLess", "source": "KeepingMore", "dest": "KeepingLess", "before": "before_keeping_less"},
            {"trigger": "StartKeepingLess", "source": "KeepingLess", "dest": "KeepingLess", "before": "before_keeping_less"},

            {"trigger": "StopKeepingMore", "source": "KeepingMore", "dest": "SteadyBlend", "before": "before_keeping_steady"},
            {"trigger": "StopKeepingLess", "source": "KeepingLess", "dest": "SteadyBlend", "before": "before_keeping_steady"},

            {"trigger": "ResetToFullySend", "source": "KeepingLess", "dest": "FullySend", "before": "before_keeping_steady"},
            {"trigger": "ResetToFullyKeep", "source": "KeepingMore", "dest": "FullyKeep", "before": "before_keeping_steady"},
        ]

        self.machine = Machine(
            model=self,
            states=SiegValveState.values(),
            transitions=self.valve_transitions,
            initial=SiegValveState.FullyKeep,
            model_attribute="valve_state",
            send_event=True,
        )
        self.valve_state: SiegValveState = SiegValveState.FullyKeep

        # --------------------------------------
        # Sieg loop state machine
        # --------------------------------------

        self.control_transitions = [
            {"trigger": "HpTurnsOff", "source": "StartupHover", "dest": "HpOff"},
            {"trigger": "HpTurnsOff", "source": "Pid", "dest": "HpOff"},
            {"trigger": "HpTurnsOn", "source": "HpOff", "dest": "StartupHover"},
            {"trigger": "LeaveStartupHover", "source": "StartupHover", "dest": "Pid"},
        ]

        self.control_machine = Machine(
            model=self,
            states=SiegControlState.values(),
            transitions=self.control_transitions,
            initial=SiegControlState.StartupHover,
            model_attribute="control_state",
            send_event=True,
        )
        self.control_state: SiegControlState = SiegControlState.StartupHover

        self.keep_seconds: float = self.FULL_RANGE_S

        self._movement_task = None
        self._main_task: asyncio.Task | None = None
        self._background_tasks: set[asyncio.Task] = set()

        self.hp_boss_state = HpBossState.HpOn
        self.target_lwt: Optional[float] = None
        self.target_lwt_time_received: Optional[float] = None

        self.control_interval_seconds = 30
        self.time_since_last_control_loop = 30
        self.time_since_last_report = 5*60
        self.hp_turned_off_time = None

        # PID parameters
        self.lwt_readings = deque(maxlen=40)
        self.lwt_slope = 0
        self._startup_hover_initialized = False
        self.ultimate_gain = 1.0  # Ku
        self.ultimate_gain_seconds = 230 # Tu
        self.pid_sensitivity = 2
        self.proportional_gain = .4 * self.pid_sensitivity #  P = 0.2*Ku
        self.derivative_gain = 15 * self.pid_sensitivity # D = 0.33 * P * Tu
        self.integral_gain = 0.00017 * self.pid_sensitivity #  I =  0.1 × P ÷ Tu
        
        # Flow percent keep from keep seconds
        self.flow_from_time_points = [
            [7,0], [9, 8], [11.2, 11.4], [14.7, 24.1], [18.2, 39.0], [22.4, 51.7],
            [28.7, 66.6], [35.7, 75.2], [39.9, 80.6], [42.7, 83.7], [67.2, 100]
        ]
        if self.flow_from_time_points[0][1] != 0:
            raise Exception("First flow point should be [x,0]!")
        if self.flow_from_time_points[-1][1] != 100:
            raise Exception("Last flow point should be [x,100]!")

        self.t1 = 26                        # seconds where some flow starts going through the Sieg Loop
        self.t2 = self.FULL_RANGE_S - 18    # seconds where all flow starts going through the Sieg Loop

    def _create_task(self, coro, *, name: str | None = None) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    # --------------------------------------
    # Main loop
    # --------------------------------------

    async def main(self):
        while not self._stop_requested:

            # In startup hover, run LWT tracking on a faster loop (every MAIN_LOOP_SLEEP_S)
            if self.control_state == SiegControlState.StartupHover:
                self.update_lwt_readings()
                self.engage_brain(called_from_main=True)
            
            # Otherwise run the pid on a slower loop (every control_interval_seconds)
            elif self.time_since_last_control_loop >= self.control_interval_seconds:
                self.time_since_last_control_loop = 0

                if self.control_state == SiegControlState.Pid:
                    self.update_lwt_readings()
                self.engage_brain(called_from_main=True)

                self._send_to(
                    self.primary_scada,
                    SingleMachineState(
                        MachineHandle=self.node.handle,
                        StateEnum=SiegControlState.enum_name(),
                        State=self.control_state,
                        UnixMs=int(time.time() * 1000),
                    ),
                )

            # Pat watchdog every 5 minutes
            if self.time_since_last_report >= 5*60:
                self.time_since_last_report = 0
                self._send(PatInternalWatchdogMessage(src=self.name))
                # TODO: Create a channel for this
                # self._send_to(
                #     self.primary_scada,
                #     SingleReading(
                #         ChannelName=H0CN.hp_keep_seconds_x_10,
                #         Value=round(self.keep_seconds * 10),
                #         ScadaReadTimeUnixMs=int(time.time() *1000)
                #     )
                # )

            self.time_since_last_control_loop += self.MAIN_LOOP_SLEEP_S
            self.time_since_last_report += self.MAIN_LOOP_SLEEP_S
            await asyncio.sleep(self.MAIN_LOOP_SLEEP_S)

    def engage_brain(self, called_from_main=False):
        self.log(f"Engaging brain, control state is {self.control_state}, hp boss state is {self.hp_boss_state}")
        active_movement = self._movement_task is not None and not self._movement_task.done()

        if self.hp_boss_state == HpBossState.HpOff:
            if self.control_state != SiegControlState.HpOff:
                self.trigger_control_event(SiegControlEvent.HpTurnsOff)
            return

        if self.control_state == SiegControlState.HpOff:
            self.trigger_control_event(SiegControlEvent.HpTurnsOn)

        if self.target_lwt is None:
            self.log("Waiting for SetTargetLwt before running PID")
            return

        if self.control_state == SiegControlState.StartupHover:
            if not self._startup_hover_initialized:
                self.enter_startup_hover()
            if active_movement:
                return
            if (
                called_from_main
                and self.hp_boss_state == HpBossState.HpOn
                and self.time_to_leave_startup_hover()
            ):
                self.trigger_control_event(SiegControlEvent.LeaveStartupHover)
            return

        if self.control_state == SiegControlState.Pid:
            if active_movement:
                self.log("Not running PID loop while valve movement is active")
                return
            if called_from_main:
                self._create_task(self.run_pid())

    # --------------------------------------
    # Startup hover
    # --------------------------------------

    def enter_startup_hover(self) -> None:
        self._startup_hover_initialized = True
        self.lwt_readings.clear()
        self.lwt_slope = 0
        self.moving_to_just_keep(SiegControlEvent.HpTurnsOn)

    def time_to_leave_startup_hover(self) -> bool:
        if self.target_lwt is None:
            return False
        lift_f = self.lift_f()
        lwt_f = self.lwt_f()
        if lift_f is None or lwt_f is None:
            self.log("Missing temperature readings during startup hover")
            return False

        target_flow_percent = self.calc_eq_flow_percent(lift_f + 3)
        if target_flow_percent is None:
            return False
        target_keep_s = self.time_from_flow(target_flow_percent)
        time_to_move = self.keep_seconds - target_keep_s

        if self.lwt_slope <= 0:
            self.log(f"Rate of change for LWT: {round(self.lwt_slope * 60, 1)} °F/min")
            return False

        time_til_target_lwt = (self.target_lwt - lwt_f) / self.lwt_slope
        if round(time.time()) % 10 == 0:
            self.log(f"Rate of change for LWT: {round(self.lwt_slope * 60, 1)} °F/min")
            self.log(f"Time until target: {round(time_til_target_lwt)}")
            self.log(f"Seconds to move valve: {round(time_to_move)}")

        return time_til_target_lwt - time_to_move < 3

    def calc_eq_flow_percent(self, lift_f: Optional[float] = None) -> Optional[float]:
        if self.target_lwt is None:
            return None
        if lift_f is None:
            lift_f = self.lift_f()
        tsc = (
            self.anticipated_sieg_cold_f()
            if self.control_state == SiegControlState.StartupHover
            else self.sieg_cold_f()
        )
        if lift_f is None or tsc is None:
            self.log("Missing temp readings for equilibrium calc")
            return None

        temp_diff = self.target_lwt - tsc
        if temp_diff <= 0:
            self.log(f"Target LWT {self.target_lwt}°F is lower than Sieg cold temp {tsc}°F")
            return 0
        k = 1 - (lift_f / temp_diff)
        return max(0, min(k, 1)) * 100

    def anticipated_sieg_cold_f(self) -> Optional[float]:
        if self.charge_discharge_relay_state() == StoreFlowRelay.DischargingStore:
            t = self.coldest_buffer_temp_f()
        else:
            t = self.coldest_store_temp_f()
        if t is None:
            t = self.sieg_cold_f()
        return t

    # --------------------------------------
    # PID functions
    # --------------------------------------

    async def run_pid(self) -> None:
        """Check current temperatures and adjust valve position if needed"""
        lwt_f = self.lwt_f()
        lift_f = self.lift_f()
        if lwt_f is None or lift_f is None:
            self.log("Missing temperature readings in PID loop!")
            return
        self.log(f"LWT {round(lwt_f,1)} | Target {round(self.target_lwt,1)} | Lift {round(lift_f,1)}")

        # Calculate target keep seconds change, and only move if significant change needed
        delta_s = self.calculate_delta_seconds(seconds_hack=True)
        if delta_s is not None and abs(delta_s) >= 0.5:
            await self._prepare_new_movement_task(delta_s) 
    
    def update_lwt_readings(self) -> None:
        lwt_f = self.lwt_f()
        if lwt_f is None:
            return
        current_time = time.time()
        self.lwt_readings.append((current_time, lwt_f))
        reference = self.lwt_reference_reading(min_age_seconds=10)
        if reference is None:
            self.lwt_slope = 0
            return
        reference_time, reference_lwt_f = reference
        time_delta_s = current_time - reference_time
        if time_delta_s <= 0:
            self.lwt_slope = 0
            return
        self.lwt_slope = (lwt_f - reference_lwt_f) / time_delta_s

    def lwt_reference_reading(self, min_age_seconds: float) -> Optional[tuple[float, float]]:
        current_time = time.time()
        for timestamp, temp in reversed(list(self.lwt_readings)[:-1]):
            if current_time - timestamp >= min_age_seconds:
                return timestamp, temp
        if len(self.lwt_readings) > 1:
            return self.lwt_readings[0]
        return None

    def calculate_delta_seconds(self, seconds_hack: bool = False) -> Optional[float]:
        """Calculate delta seconds for the next PID control interval, using
        ratio of flow as the independent variable. If seconds_hack is true, use
        the keep_seconds as the independant variable. Returns None if missing temperature readings.
        """

        if self.control_state not in [SiegControlState.Pid]:
            raise Exception(f"Should not be running PID control loop in state {self.control_state}")

        lwt_f = self.lwt_f()
        lift_f = self.lift_f()
        if lift_f is None or lwt_f is None or self.target_lwt is None:
            return None
        
        err = self.target_lwt - lwt_f
        
        # Proportional term
        proportional_term = self.proportional_gain * err
        
        # Derivative term (rate of change of error)
        current_time = time.time()
        reference = self.lwt_reference_reading(min_age_seconds=20)
        if reference is None:
            error_delta = 0
            time_delta_s = 1
        else:
            reference_time, reference_lwt_f = reference
            last_error = self.target_lwt - reference_lwt_f
            time_delta_s = current_time - reference_time
            error_delta = err - last_error
        derivative_term = self.derivative_gain * (error_delta / time_delta_s)

        # Integral term (add current error to integral, with anti-windup protection)
        if not hasattr(self, 'error_integral'): #TODO can't we just initialize this?
            self.error_integral = 0
        max_integral = 50
        self.error_integral += err * self.control_interval_seconds
        self.error_integral = max(-max_integral, min(self.error_integral, max_integral))
        integral_term = self.integral_gain * self.error_integral
        self.log("PID adjustment:")
        self.log(f"  Error: {round(err, 1)}°F")

        # Calculate total flow adjustment
        if seconds_hack:
            self.log(f"  P: {round(proportional_term, 1)} s, I: {round(integral_term, 1)} s,  D: {round(derivative_term, 1)} s")
            delta_s = proportional_term + integral_term + derivative_term
        else:
            self.log(f"  P: {round(proportional_term, 1)}% flow, I: {round(integral_term, 1)}% flow,  D: {round(derivative_term, 1)}% flow")
            flow_percent_adjustment = proportional_term + integral_term + derivative_term
            
            # Convert to time_percent_keep
            flow_percent_keep = self.flow_from_time(self.keep_seconds)
            target_flow_percent = flow_percent_keep + flow_percent_adjustment
            target_time_s = self.time_from_flow(target_flow_percent)
            delta_s = target_time_s - self.keep_seconds
            self.log(f"  Flow target: {round(target_flow_percent,1)}%")
            self.log(f"  Flow adjustment: {round(flow_percent_adjustment,1)}%")

        # Bound the adjustment to the physical limits of the valve
        if delta_s > 0:
            bounded_adjustment = min(delta_s, self.control_interval_seconds)
        else:
            bounded_adjustment = max(delta_s, -self.control_interval_seconds)
        target_keep_seconds = max(
            0,
            min(self.FULL_RANGE_S, self.keep_seconds + bounded_adjustment),
        )
        bounded_adjustment = target_keep_seconds - self.keep_seconds
        self.log(f"  Time adjustment: {round(delta_s,1)} seconds")
        self.log(f"  Bounded time adjustment: {round(bounded_adjustment,1)} seconds")
        return bounded_adjustment

    def flow_from_time(self, time_s: float) -> float:
        """
        Convert valve position in seconds (time_s,  seconds from valve 
        at its fully send stop endpoint) to actual flow percentage (flow_percent_keep)
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
        """
        Convert actual flow percentage (flow_percent_keep) to valve position
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
        
        for i in range(1, len(points)):
            x0, y0 = points[i - 1]
            x1, y1 = points[i]
            if x0 <= x <= x1:
                y = (x - x0) * (y1 - y0) / (x1 - x0) + y0
                return y

        raise Exception("time_from_flow requires flow_percent_keep between 0 and 100")

    # --------------------------------------
    # Control State Machine
    # --------------------------------------

    def trigger_control_event(self, event: SiegControlEvent) -> None:
        now_ms = int(time.time() * 1000)
        orig_state = self.control_state

        control_fn = getattr(self, event)
        if control_fn:
            control_fn(self)
        else:
            raise Exception(f"Unknown control event {event}")
        
        self.log(f"{event}: {orig_state} -> {self.control_state}")
        if self.control_state == orig_state:
            self.log(f"Warning: event {event} did not cause a change in control state")
            return

        if self.control_state == SiegControlState.HpOff:
            self._startup_hover_initialized = False
            self.time_since_last_control_loop = 0
            self.moving_to_full_keep(event)
        elif self.control_state == SiegControlState.StartupHover:
            self.time_since_last_control_loop = 0
            self.enter_startup_hover()
        elif self.control_state == SiegControlState.Pid:
            self._startup_hover_initialized = False
            self.time_since_last_control_loop = 0
            self.log("Startup hover complete, entering PID loop")
            self._create_task(self.move_to_pid_target())

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
    
    def moving_to_full_send(self, event: SiegControlEvent) -> None:
        if self.valve_state == SiegValveState.FullySend and self.keep_seconds <= 0:
            self.log("Already at full send")
            return
        self.log("Moving to full send")
        self._create_task(self._prepare_new_movement_task(-self.keep_seconds - 10))

    def moving_to_full_keep(self, event: SiegControlEvent) -> None:
        if self.valve_state == SiegValveState.FullyKeep and self.keep_seconds >= self.FULL_RANGE_S:
            self.log("Already at full keep")
            return
        self.log("Moving to full keep position (overshoot the full range by 10 seconds to be safe)")
        self._create_task(self._prepare_new_movement_task(-self.keep_seconds + self.FULL_RANGE_S + 10))

    def moving_to_just_keep(self, event: SiegControlEvent) -> None:
        self.log("Moving to just keep position")
        self._create_task(self._prepare_new_movement_task(-self.keep_seconds + self.t2))

    async def move_to_pid_target(self) -> None:
        lift_f = self.lift_f()
        if lift_f is None:
            self.log("Missing lift reading while moving to PID target")
            return
        flow_target_percent = self.calc_eq_flow_percent(lift_f + 3)
        if flow_target_percent is None:
            return
        keep_seconds_target = self.time_from_flow(flow_target_percent)
        delta_s = keep_seconds_target - self.keep_seconds
        self.log(f"Calculated PID target: {round(keep_seconds_target, 1)} seconds")
        if abs(delta_s) >= 0.5:
            await self._prepare_new_movement_task(delta_s)

    # --------------------------------------
    # Valve State Machine
    # --------------------------------------

    def trigger_valve_event(self, event: SiegValveEvent) -> None:
        orig_state = self.valve_state 

        control_fn = getattr(self, event)
        if control_fn:
            control_fn(self)
        else:
            raise Exception(f"Unknown control event {event}")
        
        self.log(f"{event}: {orig_state} -> {self.valve_state}")
        if self.valve_state == orig_state:
            self.log(f"Warning: event {event} did not cause a change in valve state")
            return

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

    def before_keeping_more(self, event: SiegValveEvent) -> None:
        self.change_to_hp_keep_more()
        self.sieg_valve_active()

    def before_keeping_less(self, event: SiegValveEvent) -> None:
        self.change_to_hp_keep_less()
        self.sieg_valve_active()

    def before_keeping_steady(self, event: SiegValveEvent) -> None:
        self.sieg_valve_dormant()

    # --------------------------------------
    # Message processing
    # --------------------------------------

    def process_message(self, message: Message[Any]) -> Result[bool, Exception]:
        from_node = self.layout.node(message.Header.Src, None)
        if from_node is None:
            return Ok(False)
           
        payload = message.Payload
        match payload:
            case ActuatorsReady():
                self.send_info("Received an actuators ready message, should not be in PID mode!")
            case SingleMachineState():
                self.process_single_machine_state(from_node, payload)
            case SetTargetLwt():
                self.process_set_target_lwt(from_node, payload)
            case FsmFullReport():
                pass
            case _: 
                self.log(f"{self.name} received unexpected message: {message.Header}")
        return Ok(True)

    def process_single_machine_state(self, from_node: ShNode, payload: SingleMachineState) -> None:
        self.log(f"Just received state {payload.State} from HpBoss")
        if payload.StateEnum != HpBossState.enum_name():
            raise Exception(f"The StateEnum {payload.StateEnum}is not a HpBossState enum: {HpBossState.enum_name()}")
        if from_node != self.hp_boss:
            raise Exception("Not expecting single machine state messages except from HpBoss")

        if (
            payload.State == HpBossState.HpOff
            and self.hp_boss_state != HpBossState.HpOff
        ):
            self.hp_turned_off_time = time.time()

        if (
            payload.State == HpBossState.PreparingToTurnOn
            and self.hp_boss_state != HpBossState.PreparingToTurnOn
        ):
            self.log("Sending SiegLoopReady to HpBoss")
            self._send_to(self.hp_boss, SiegLoopReady())

        self.hp_boss_state = payload.State
        self.engage_brain()             

    def process_set_target_lwt(self, from_node: ShNode, payload: SetTargetLwt) -> None:
        if payload.ToHandle != self.node.handle:
            self.log(f"Ignoring SetTargetLwt with ToHandle {payload.ToHandle} != {self.node.handle}")
            return
        if from_node.Handle != payload.FromHandle:
            raise Exception(f"from_node handle {from_node.Handle} does not match payload {payload.FromHandle}")
        boss = self.layout.boss_node(self.node)
        if boss is None:
            raise Exception(f"No boss found for node {self.node.handle}")
        if payload.FromHandle != boss.Handle:
            raise Exception(f"Invalid SetTargetLwt: {payload.FromHandle} is not boss of this node, {boss.Handle} is")
   
        self.log(f"Boss set target LWT to {payload.TargetLwtF}°F ({from_node.Name})")
        self.target_lwt = float(payload.TargetLwtF)
        self.target_lwt_time_received = time.time()

    # --------------------------------------
    # Movements
    # --------------------------------------

    def complete_move(self, task_id: str) -> None:
        if self.valve_state == SiegValveState.KeepingMore:
            self.trigger_valve_event(SiegValveEvent.StopKeepingMore)

        elif self.valve_state == SiegValveState.KeepingLess:
            self.trigger_valve_event(SiegValveEvent.StopKeepingLess)

        self.log(f"Movement {task_id} completed: {round(self.keep_seconds, 1)} seconds, state {self.valve_state}")

    async def clean_up_old_task(self) -> None:
        if hasattr(self, '_movement_task') and self._movement_task and not self._movement_task.done():
            self.log(f"Cancelling movement task {self._current_task_id}")
            self._movement_task.cancel()
            
            # Wait for the task to actually complete
            try:
                await asyncio.wait_for(self._movement_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                self.log("Cancelled previous task")
            
            # Ensure proper state cleanup regardless of how the task ended
            if self.valve_state == SiegValveState.KeepingMore:
                self.trigger_valve_event(SiegValveEvent.StopKeepingMore)
                self.log("Triggered StopKeepingMore after cancellation")
            
            elif self.valve_state == SiegValveState.KeepingLess:
                self.trigger_valve_event(SiegValveEvent.StopKeepingLess)
                self.log("Triggered StopKeepingLess after cancellation")

            # Set task to None after cancellation
            self._movement_task = None

    async def _prepare_new_movement_task(self, delta_s: float):
        """Create a new movement task adding delta_s to the current keep seconds."""
        await self.clean_up_old_task()
        
        new_task_id = str(uuid.uuid4())[-4:]
        self._current_task_id = new_task_id

        if delta_s > 0:
            self.log(f"Task {new_task_id}: move to keep for {round(delta_s,1)} seconds")
        else:
            self.log(f"Task {new_task_id}: move to send for {round(-delta_s,1)} seconds")
        
        self._movement_task = self._create_task(self._adjust_keep_seconds(delta_s, new_task_id))
    
    async def _adjust_keep_seconds(self, delta_s: float, task_id: str) -> None:
        """Move the valve by adding delta_s to the current keep seconds."""
        if delta_s == 0:
            self.log("Already at target, delta_s is 0 seconds")
            return

        try:
            # Moving to keeping more
            if delta_s>0:
                if self.valve_state == SiegValveState.FullyKeep and self.keep_seconds >= self.FULL_RANGE_S:
                    self.log("Already at full keep")
                    return
                self.trigger_valve_event(SiegValveEvent.StartKeepingMore)
                # Process the movement in a loop
                delta_so_far = 0
                while delta_so_far < delta_s:
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

            # Moving to sending more
            else:
                if self.valve_state == SiegValveState.FullySend and self.keep_seconds <= 0:
                    self.log("Already at full send")
                    return
                self.trigger_valve_event(SiegValveEvent.StartKeepingLess)
                # Now process the movement in a loop
                delta_so_far = 0
                while delta_so_far > delta_s:
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

            if task_id == self._current_task_id:
                self.complete_move(task_id)

        except asyncio.CancelledError:
            self.log(f"Movement cancelled at {self.keep_seconds} seconds from FullSend")
            raise
        except Exception as e:
            self.log(f"Error during movement: {e}")
            self.complete_move(task_id)

        finally:
            self._movement_task = None

    async def _keep_less(self, start_s: float, task_id: str, fraction: Optional[float] = None) -> None:
        """Keep 1 second (or, if specified, a fraction) less"""

        if task_id != self._current_task_id:
            return
        if self.valve_state != SiegValveState.KeepingLess:
            raise Exception(f"Only call _keep_one_percent_less in state KeepingLess, not {self.valve_state}")
            
        # Calculate the sleep time
        sleep_s = 1
        if fraction:
            if fraction > 1:
                raise Exception("fraction needs to be less than 1")
            sleep_s = fraction
        
        orig_keep_seconds = self.keep_seconds
        
        # Sleep for the calculated time
        await asyncio.sleep(sleep_s)
        if task_id != self._current_task_id:
            return

        # Calculate the new keep seconds
        now = time.time()
        delta_s = now - start_s
        self.keep_seconds = max(0, orig_keep_seconds - delta_s)

        # TODO
        # self._send_to(
        #     self.primary_scada,
        #     SingleReading(
        #         ChannelName=H0CN.hp_keep_seconds_x_10,
        #         Value=round(self.keep_seconds * 10),
        #         ScadaReadTimeUnixMs=int(time.time() *1000)
        #     )
        # )

    async def _keep_more(self, start_s: float, task_id: str, fraction: Optional[float] = None) -> None:
        """Or keep fraction percent more ... REQUIRES fraction to be less than 1"""
        # Check if we're still the current task
        if task_id != self._current_task_id:
            return
        if self.valve_state != SiegValveState.KeepingMore:
            raise Exception(f"Only call _keep_one_percent_more in state KeepingMore, not {self.valve_state}")

        # Calculate the sleep time
        sleep_s = 1
        if fraction:
            if fraction > 1:
                raise Exception("fraction needs to be less than 1")
            sleep_s = fraction

        orig_keep_seconds = self.keep_seconds

        # Sleep for the calculated time
        await asyncio.sleep(sleep_s)
        if task_id != self._current_task_id:
            return

        # Calculate the new keep seconds
        now = time.time()
        delta_s = now - start_s
        self.keep_seconds = min(self.FULL_RANGE_S, orig_keep_seconds + delta_s)

        # TODO
        # self._send_to(
        #     self.primary_scada,
        #     SingleReading(
        #         ChannelName=H0CN.hp_keep_seconds_x_10,
        #         Value=round(self.keep_seconds * 10),
        #         ScadaReadTimeUnixMs=int(time.time() *1000)
        #     )
        # )

    # --------------------------------------
    # Required methods and properties
    # --------------------------------------

    def start(self) -> None:
        self._stop_requested = False
        self._main_task = self._create_task(
            self.main(),
            name="Sieg Loop PID Synchronous Report",
        )
        self.services.add_task(self._main_task)

    def stop(self) -> None:
        self._stop_requested = True
        if self._movement_task and not self._movement_task.done():
            self._movement_task.cancel()
            try:
                if self.valve_state == SiegValveState.KeepingMore:
                    self.trigger_valve_event(SiegValveEvent.StopKeepingMore)
                elif self.valve_state == SiegValveState.KeepingLess:
                    self.trigger_valve_event(SiegValveEvent.StopKeepingLess)
            except Exception as e:
                self.log(f"Trouble stopping valve movement: {e}")
        if self._main_task and not self._main_task.done():
            self._main_task.cancel()
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()

    async def join(self) -> None:
        if self._background_tasks:
            await asyncio.gather(
                *list(self._background_tasks),
                return_exceptions=True,
            )
    
    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, 400)]
