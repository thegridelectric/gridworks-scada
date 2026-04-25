import time
import uuid
import asyncio
from enum import auto
from result import Ok, Result
from transitions import Machine
from typing import Any, Optional, Sequence

from gw_spaceheat.scada_app_interface import ScadaAppInterface
from gwproto.message import Message
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums.gw_str_enum import GwStrEnum
from gw_spaceheat.actors.hp_boss import SiegLoopReady
from gwsproto.enums.hp_boss_state import HpBossState
from gw_spaceheat.actors.sh_node_actor import ShNodeActor
from gwsproto.named_types import ActuatorsReady, SingleMachineState


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
    Initializing = auto()
    Blind = auto()
    HpOff = auto()
    HpStartingUp = auto()
    HpHasLift = auto()

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.sieg.control.state"


class SiegControlEvent(GwStrEnum):
    DoneInitializingBlind = auto()
    DoneInitializingHpOn = auto()
    DoneInitializingHpOff = auto()
    DoneInitializingHpStartingUp = auto()
    BecameBlind = auto()
    NoLongerBlindHpOn = auto()
    NoLongerBlindHpOff = auto()
    NoLongerBlindHpStartingUp = auto()
    HpTurnsOff = auto()
    HpTurnsOn = auto()
    HpStartUpDone = auto()


class SiegLoop(ShNodeActor):
    FULL_RANGE_S = 100

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
            # Initializing
            {"trigger": "DoneInitializingBlind", "source": "Initializing", "dest": "Blind"},
            {"trigger": "DoneInitializingHpOn", "source": "Initializing", "dest": "HpHasLift"},
            {"trigger": "DoneInitializingHpOff", "source": "Initializing", "dest": "HpOff"},
            {"trigger": "DoneInitializingHpStartingUp", "source": "Initializing", "dest": "HpStartingUp"},

            # Turning off the heat pump
            {"trigger": "HpTurnsOff", "source": "HpStartingUp", "dest": "HpOff"},
            {"trigger": "HpTurnsOff", "source": "HpHasLift", "dest": "HpOff"},

            # Turning on the heat pump
            {"trigger": "HpTurnsOn", "source": "HpOff", "dest": "HpStartingUp"},

            # Reaching the end of the heat pump startup
            {"trigger": "HpStartUpDone", "source": "HpStartingUp", "dest": "HpHasLift"},

            # Going / leaving Blind state
            {"trigger": "BecameBlind", "source": "*", "dest": "Blind"},
            {"trigger": "NoLongerBlindHpOn", "source": "Blind", "dest": "HpHasLift"},
            {"trigger": "NoLongerBlindHpOff", "source": "Blind", "dest": "HpOff"},
            {"trigger": "NoLongerBlindHpStartingUp", "source": "Blind", "dest": "HpStartingUp"},
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

        self.keep_seconds: float = self.FULL_RANGE_S

        self._movement_task = None

        self.hp_boss_state = HpBossState.HpOn

        self.actuators_ready: bool = False
        self.control_interval_seconds = 30
        self.time_since_last_report = 5*60
        self.hp_turned_off_time = None

        self.t1 = 26                        # seconds where some flow starts going through the Sieg Loop
        self.t2 = self.FULL_RANGE_S - 18    # seconds where all flow starts going through the Sieg Loop

    # --------------------------------------
    # Main loop
    # --------------------------------------
    
    async def main(self):
        while not self._stop_requested:
            self.engage_brain()

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

            self.time_since_last_report += self.control_interval_seconds
            await asyncio.sleep(self.control_interval_seconds)

    def hp_loop_is_getting_hot(self):
        lwt = self.lwt_f()
        ewt = self.ewt_f()
        
        if self.is_blind() or not lwt or not ewt:
            self.log(f"Warning: hp_loop_is_getting_hot called but blind")
            return True
        
        threshold_lwt = self.data.ha1_params.MaxEwtF-20
        if max(lwt, ewt) > threshold_lwt:
            return True
        return False

    def engage_brain(self):
        self.log(f"Engaging brain, control state is {self.control_state}, hp boss state is {self.hp_boss_state}")
        # Check if actuators are ready
        if self.control_state == SiegControlState.Initializing:
            if self.actuators_ready:
                if self.is_blind():
                    self.trigger_control_event(SiegControlEvent.DoneInitializingBlind)
                elif self.hp_boss_state == HpBossState.HpOff:
                    self.trigger_control_event(SiegControlEvent.DoneInitializingHpOff)
                elif self.hp_boss_state == HpBossState.PreparingToTurnOn:
                    self.trigger_control_event(SiegControlEvent.DoneInitializingHpStartingUp)
                elif self.hp_boss_state == HpBossState.HpOn:
                    if self.hp_loop_is_getting_hot():
                        self.trigger_control_event(SiegControlEvent.DoneInitializingHpOn)
                    else:
                        self.trigger_control_event(SiegControlEvent.DoneInitializingHpStartingUp)
            else:
                self.log(f"Waiting for actuators to be ready to get out of Initializing state")
                return
        
        # Get in/out of Blind state
        if self.control_state != SiegControlState.Blind and self.is_blind():
            self.trigger_control_event(SiegControlEvent.BecameBlind)
        elif self.control_state == SiegControlState.Blind and not self.is_blind():
            if self.hp_boss_state == HpBossState.HpOff:
                self.trigger_control_event(SiegControlEvent.NoLongerBlindHpOff)
            elif self.hp_boss_state == HpBossState.PreparingToTurnOn:
                self.trigger_control_event(SiegControlEvent.NoLongerBlindHpStartingUp)
            elif self.hp_boss_state == HpBossState.HpOn:
                if self.hp_loop_is_getting_hot():
                    self.trigger_control_event(SiegControlEvent.NoLongerBlindHpOn)
                else:
                    self.trigger_control_event(SiegControlEvent.NoLongerBlindHpStartingUp)

        if self.control_state == SiegControlState.Blind:
            return

        # Adapt state if not Blind
        if self.control_state != SiegControlState.HpOff and self.hp_boss_state == HpBossState.HpOff:
            self.trigger_control_event(SiegControlEvent.HpTurnsOff)
        elif (
            self.control_state not in [SiegControlState.HpStartingUp, SiegControlState.HpHasLift] 
            and self.hp_boss_state in [HpBossState.PreparingToTurnOn, HpBossState.HpOn]
        ):
            self.trigger_control_event(SiegControlEvent.HpTurnsOn)
        elif self.control_state == SiegControlState.HpStartingUp:
            if self.hp_loop_is_getting_hot():
                self.trigger_control_event(SiegControlEvent.HpStartUpDone)

    def is_blind(self) -> bool:
        if self.lift_f() is None:
            return True
        if self.total_hp_pwr_w() is None:
            return True
        if self.hp_turned_off_time is not None and time.time()-self.hp_turned_off_time>120:
            if self.total_hp_pwr_w() > 500:
                return True
        return False        

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

        # Manually call the appropriate callback based on the new state
        if self.control_state == SiegControlState.Blind:
            self.moving_to_full_send(event)
        elif self.control_state == SiegControlState.HpOff:
            self.moving_to_full_keep(event)
        elif self.control_state == SiegControlState.HpStartingUp:
            self.moving_to_just_keep(event)
        elif self.control_state == SiegControlState.HpHasLift:
            self.moving_to_full_send(event)

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
        self.log(f"Moving to full send")
        asyncio.create_task(self._prepare_new_movement_task(-self.keep_seconds - 10))

    def moving_to_full_keep(self, event: SiegControlEvent) -> None:
        self.log(f"Moving to full keep position (overshoot the full range by 10 seconds to be safe)")
        asyncio.create_task(self._prepare_new_movement_task(-self.keep_seconds + self.FULL_RANGE_S + 10))

    def moving_to_just_keep(self, event: SiegControlEvent) -> None:
        self.log(f"Moving to just keep position")
        asyncio.create_task(self._prepare_new_movement_task(-self.keep_seconds + self.t2))

    # --------------------------------------
    # Valve State Machine
    # --------------------------------------

    def trigger_valve_event(self, event: SiegValveEvent) -> None:
        now_ms = int(time.time() * 1000)
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
                self.actuators_ready = True
                self.engage_brain()
            case SingleMachineState():
                self.process_single_machine_state(from_node, payload)
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
            self.log(f"Sending SiegLoopReady to HpBoss")
            self._send_to(self.hp_boss, SiegLoopReady())

        self.hp_boss_state = payload.State
        self.engage_brain()             

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
                self.log(f"Triggered StopKeepingMore after cancellation")
            
            elif self.valve_state == SiegValveState.KeepingLess:
                self.trigger_valve_event(SiegValveEvent.StopKeepingLess)
                self.log(f"Triggered StopKeepingLess after cancellation")

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
        
        self._movement_task = asyncio.create_task(self._adjust_keep_seconds(delta_s, new_task_id))
    
    async def _adjust_keep_seconds(self, delta_s: float, task_id: str) -> None:
        """Move the valve by adding delta_s to the current keep seconds."""
        if delta_s == 0:
            self.log(f"Already at target, delta_s is 0 seconds")
            return

        try:
            # Moving to keeping more
            if delta_s>0:
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

            # Moving to keeping less
            else:
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
        self.services.add_task(asyncio.create_task(self.main(), name="Sieg Loop Synchronous Report"))

    def stop(self) -> None:
        self._stop_requested = True

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""
        ...
    
    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, 400)]
