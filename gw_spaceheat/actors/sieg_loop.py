import time
import uuid
import asyncio
from enum import auto
from result import Ok, Result
from transitions import Machine
from typing import List, Optional, Sequence

from scada_app_interface import ScadaAppInterface
from gwproto.message import Message
from gwsproto.data_classes.house_0_names import H0CN
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.named_types import FsmFullReport, SingleReading, AnalogDispatch
from gwsproto.enums.gw_str_enum import GwStrEnum
from actors.hp_boss import SiegLoopReady, HpBossState
from actors.sh_node_actor import ShNodeActor
from gwsproto.enums import HpModel
from gwsproto.named_types import ActuatorsReady, ResetHpKeepValue, SingleMachineState


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
    def values(cls) -> List[str]:
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
    MAIN_LOOP_SLEEP_S = 2
    flow_percent_from_seconds = [
        [7,0], [9, 8], [11.2, 11.4], [14.7, 24.1], [18.2, 39.0], [22.4, 51.7],
        [28.7, 66.6], [35.7, 75.2], [39.9, 80.6], [42.7, 83.7], [67.2, 100]
    ]

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
            {"trigger": "NoLongerBlindHpOn", "source": "Blind", "dest": "HpStartingUp"},
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

        self.keep_seconds: float = self.FULL_RANGE_S # TODO: check if this is still correct
        self.log(f"Starting with keep seconds at {self.keep_seconds} s")

        self._movement_task = None
        self.move_start_s: float = 0

        self.hp_boss_state = HpBossState.HpOn
        self.hp_start_s: float = time.time()
        self.hp_model = self.settings.hp_model

        self.actuators_ready: bool = False
        self.control_interval_seconds = 30
        self.time_since_last_report = 5*60
        self.resetting = False # TODO: check if this is still usefull

        self.t1 = 26                        # seconds where some flow starts going through the Sieg Loop
        self.t2 = self.FULL_RANGE_S - 18    # seconds where all flow starts going through the Sieg Loop

        if self.flow_percent_from_seconds[0][1] != 0:
            raise Exception(f"First flow point should be [x,0]!")

        if self.flow_percent_from_seconds[-1][1] != 100:
            raise Exception(f"Last flow point should be [x,100]!")

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
                    if self.lift_f() and self.lift_f() > 5 and time.time()-self.hp_start_s > 60:
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
                self.trigger_control_event(SiegControlEvent.NoLongerBlindHpOn)
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
            if self.lift_f() and self.lift_f() > 5 and time.time()-self.hp_start_s > 60:
                self.trigger_control_event(SiegControlEvent.HpStartUpDone)

    def is_blind(self) -> bool:
        if self.lift_f() is None:
            return True
        return False        

    # --------------------------------------
    # Control State Machine
    # --------------------------------------

    def trigger_control_event(self, event: SiegControlEvent) -> None:
        self.log(f"Triggering control event {event}, control state is {self.control_state}")
        if self.resetting:
            raise Exception("Do not interrupt resetting to fully send or fully keep!")

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
    
    def moving_to_full_send(self, event):
        self.log(f"Moving to full send")
        asyncio.create_task(self._prepare_new_movement_task(-self.keep_seconds - 10))

    def moving_to_full_keep(self, event):
        self.log(f"Moving to full keep position")
        asyncio.create_task(self._prepare_new_movement_task(-self.keep_seconds + self.FULL_RANGE_S + 10))

    def moving_to_just_keep(self, event):
        self.log(f"Moving to just keep position to prepare for heat pump start")
        asyncio.create_task(self._prepare_new_movement_task(-self.keep_seconds + self.t2))

    # --------------------------------------
    # Valve State Machine
    # --------------------------------------

    def trigger_valve_event(self, event: SiegValveEvent) -> None:
        if self.resetting:
            raise Exception("Do not interrupt resetting to fully send or fully keep!")

        now_ms = int(time.time() * 1000)
        orig_state = self.valve_state 

        # Trigger the state machine transition
        if event == SiegValveEvent.StartKeepingMore:
            self.StartKeepingMore()
        elif event == SiegValveEvent.StartKeepingLess:
            self.StartKeepingLess()
        elif event == SiegValveEvent.StopKeepingMore:
            self.StopKeepingMore()
        elif event == SiegValveEvent.StopKeepingLess:
            self.StopKeepingLess()
        elif event == SiegValveEvent.ResetToFullySend:
            self.ResetToFullySend()
        elif event == SiegValveEvent.ResetToFullyKeep:
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

    def before_keeping_more(self, event):
        self.change_to_hp_keep_more()
        self.sieg_valve_active()
        self.move_start_s = time.time()

    def before_keeping_less(self, event):
        self.change_to_hp_keep_less()
        self.sieg_valve_active()
        self.move_start_s = time.time()

    def before_keeping_steady(self, event):
        self.sieg_valve_dormant()

    # --------------------------------------
    # Message processing
    # --------------------------------------

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        from_node = self.layout.node(message.Header.Src, None)
        if from_node is None:
            return Ok(False)
           
        payload = message.Payload
        match payload:
            case ActuatorsReady():
                self.actuators_ready = True
                self.engage_brain()
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
            case SingleMachineState():
                self.process_single_machine_state(from_node, payload)
            case _: 
                self.log(f"{self.name} received unexpected message: {message.Header}"
            )
        return Ok(True)

    async def process_analog_dispatch(self, from_node: ShNode, payload: AnalogDispatch) -> None:    
        # TODO: fix this later
        # if from_node != self.boss:
        #     self.log(f"sieg loop expects commands from its boss {self.boss.Handle}, not {from_node.Handle}")
        #     return
        # if self.boss.handle != payload.FromHandle:
        #     self.log(f"boss's handle {self.boss.handle} does not match payload FromHandle {payload.FromHandle}")
        #     return

        # Move to the target seconds
        target_s = payload.Value
        self.log(f"Received command to set valve to {target_s} seconds")
        delta_s = target_s - self.keep_seconds
        asyncio.create_task(self._prepare_new_movement_task(delta_s))

    def process_reset_hp_keep_value(self, from_node: ShNode, payload: ResetHpKeepValue) -> None:
        self.log("Got ResetHpKeepValue")
        if from_node != self.boss:
            self.log(f"sieg loop expects commands from its boss {self.boss.Handle}, not {from_node.Handle}")
            return
        if self.boss.handle != payload.FromHandle:
            self.log(f"boss's handle {self.boss.handle} does not match payload FromHandle {payload.FromHandle}")
            return
        if self._movement_task:
            self.send_info("[SiegValve] Not resetting hp keep value while moving")
            return
        
        # Reset the keep seconds without moving the valve
        self.log(f"Resetting keep seconds from {self.keep_seconds} to {payload.HpKeepSecondsTimes10 / 10} without moving valve")
        self.keep_seconds = payload.HpKeepSecondsTimes10 / 10
        # TODO
        # self._send_to(
        #     self.primary_scada,
        #     SingleReading(
        #         ChannelName=H0CN.hp_keep_seconds_x_10,
        #         Value=round(self.keep_seconds * 10),
        #         ScadaReadTimeUnixMs=int(time.time() *1000)
        #     )
        # )

    def process_single_machine_state(self, from_node: ShNode, payload: SingleMachineState) -> None:
        self.log(f"Just received state {payload.State} from HpBoss")
        if payload.StateEnum != HpBossState.enum_name():
            raise Exception(f"The StateEnum {payload.StateEnum}is not a HpBossState enum: {HpBossState.enum_name()}")
        if from_node != self.hp_boss:
            raise Exception("Not expecting single machine state messages except from HpBoss")

        if self.hp_boss_state != HpBossState.HpOn and payload.State == HpBossState.HpOn:
            self.hp_start_s = time.time()

        if self.hp_boss_state == HpBossState.PreparingToTurnOn:
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

        # Adding delta_s to the current keep seconds
        target_seconds = self.keep_seconds + delta_s

        # Set the appropriate state
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

            # At the end of the method, after movement is complete:
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

    async def keep_harder(self, seconds: int, task_id: str) -> None:
        try:
            if self.valve_state != SiegValveState.FullyKeep:
                self.log("Use only when in FullyKeep")
                return
            self.change_to_hp_keep_more()
            self.sieg_valve_active()
            self.send_info(f"[SiegValve {task_id}] Keeping for {seconds} seconds more")
            await asyncio.sleep(seconds)
            if task_id != self._current_task_id:
                self.log(f"Task {task_id} has been superseded!")
            else:
                self.sieg_valve_dormant()
        except asyncio.CancelledError:
            self.log("keep_harder task cancelled")
            raise
        except Exception as e:
            self.log(f"Error during keep_harder: {e}")
            self.sieg_valve_dormant()
            self.send_error(f"Error during keep_harder: {e}")
        finally:
            self._movement_task = None
            self.log(f"Task {task_id} complete")

    async def send_harder(self, seconds: int, task_id: str) -> None:
        try:
            if self.valve_state != SiegValveState.FullySend:
                self.log("Use when in FullySend")
                return
            self.change_to_hp_keep_less()
            self.sieg_valve_active()
            self.send_info(f"[SiegLoop{task_id}] Sending for {seconds} seconds more")
            await asyncio.sleep(seconds)
            if task_id != self._current_task_id:
                self.log(f"Task {task_id} has been superseded!")
            else:
                self.sieg_valve_dormant()
        except asyncio.CancelledError:
            self.log("send_harder task cancelled")
            raise
        except Exception as e:
            self.log(f"Error during send_harder: {e}")
            self.sieg_valve_dormant()
            self.send_error(f"Error during send_harder: {e}")
        finally:
            self._movement_task = None
            self.log(f"Task {task_id} complete")

    ##############################################
    # Flow related conversions
    ##############################################

    def flow_percent_from_time(self, time_s: float) -> float:
        """
        Convert valve position in seconds (time_s,  seconds from valve 
        at its fully send stop endpoint) to actual flow percentage (flow_percent_keep)
        """
        # Time to flow points (experimental)
        points =  self.flow_percent_from_seconds
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

    def time_from_flow_percent(self, flow_percent_keep: float) -> float:
        """
        Convert actual flow percentage (flow_percent_keep) to valve position
        (seconds from valve at its fully send stop endpoint)
        """
        points = []
        for point in self.flow_percent_from_seconds:
            points.append([point[1], point[0]])

        # Bound the flow percent keep between 0 and 100
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

        raise Exception(f"time_from_flow_percent requires flow_percent_keep between 0 and 100")

    @property
    def flow_percent_keep(self) -> float:
        """Calculate the current flow percentage through the keep path based on valve position"""
        return self.flow_percent_from_time(self.keep_seconds)

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
