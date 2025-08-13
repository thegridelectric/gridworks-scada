import time
import uuid
import asyncio
from typing import List, Literal
from pydantic import BaseModel
from data_classes.house_0_names import H0CN, H0N
from enum import auto
from gw.enums import GwStrEnum
from gwproto.message import Message
from gwproto.data_classes.sh_node import ShNode
from gwproto.named_types import AnalogDispatch, FsmFullReport
from gwproto.enums import ChangeRelayState
from result import Ok, Result


from actors.scada_actor import ScadaActor
from enums import LogLevel, TurnHpOnOff
from named_types import ActuatorsReady, FsmEvent, Glitch, SingleMachineState
from scada_app_interface import ScadaAppInterface


class SiegLoopReady(BaseModel):
    TypeName: Literal["sieg.loop.ready"] = "sieg.loop.ready"
    Version: str = "000"

class HpBossState(GwStrEnum):
    PreparingToTurnOn = auto()
    HpOn = auto()
    HpOff = auto()

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "hp.boss.state"

class HpBoss(ScadaActor):
    """
    Direct Reports:
    HpBoss
        ├── HpScadaOps
        └── SiegLoop
    """
    TURN_ON_ANYWAY_S = 120 # turn on the heat pump after 2 minutes without strat-boss
    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self.hp_model = self.settings.hp_model # TODO: will move to hardware layout
        self.last_cmd_time = 0
        self.actuators_ready = False
        self.state = HpBossState.HpOn

    def start(self) -> None:
        """ Required method, used for starting long-lived tasks. Noop."""
        ...

    def stop(self) -> None:
        """ Required method, used for stopping tasks. Noop"""
        ...

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""
        ...

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        from_node = self.layout.node(message.Header.Src, None)
        if from_node is None:
            return Ok(False)
        payload = message.Payload
        match payload:
            case ActuatorsReady():
                self.actuators_ready = True
            case FsmEvent():
                try:
                    self.process_fsm_event(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_fsm_event: {e}")
            case FsmFullReport():
                ... # relay reports back with ack of change if we care
            case SiegLoopReady():
                try:
                    self.process_sieg_loop_ready(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_sieg_loop_ready: {e}")
            case _: 
                self.log(f"{self.name} received unexpected message: {message.Header}"
            )
        return Ok(True)
    

    def process_fsm_event(self, from_node: ShNode, payload: FsmEvent) -> None: 
        self.log(f"Got {payload}")   
        if payload.ToHandle != self.node.handle:
             # TODO: turn this into a report?
            self._send_to(self.atn,
                          Glitch(
                              FromGNodeAlias=self.layout.scada_g_node_alias,
                              Node=self.name,
                              Type=LogLevel.Warning,
                              Summary="bad_boss",
                              Details=f"{payload.FromHandle} tried to command {self.node.Handle}. Ignoring!"
                          ))
            self.log(f"Handle is {self.node.Handle}; ignoring {payload}")
        if from_node.handle != payload.FromHandle:
            self.log(
                f"from_node {from_node.name} has handle {from_node.handle}, not {payload.FromHandle}!"
            )
            # TODO: probably send glitch here as well
        # TODO: add way for boss to realize its command was ignored before
        # adding the following
        # if time.time() - self.last_cmd_time < 0.5:
        #     self.log("IGNORING COMMAND ")
        if payload.EventType !=  TurnHpOnOff.enum_name():
            self.log(f"Only listens to {TurnHpOnOff.enum_name()}")
            return
        if not self.actuators_ready:
            self.log(f"Received command {payload.EventName} for heat pump but actuators not ready. Ignoring")
            return
        if payload.EventName == TurnHpOnOff.TurnOff:
            self.open_hp_scada_ops_relay()
            self.state = HpBossState.HpOff
            self._send_to(self.primary_scada,
                          SingleMachineState(
                              MachineHandle=self.node.handle,
                              StateEnum=HpBossState.enum_name(),
                              State=self.state,
                              UnixMs=int(time.time() * 1000)
                          ))
        elif self.state == HpBossState.HpOff:
            # HpOff -> PreparingToTurnOn
            if self.layout.use_sieg_loop:
                self.state = HpBossState.PreparingToTurnOn
                # self._send_to(self.primary_scada, dispatch)
                self._send_to(self.primary_scada,
                            SingleMachineState(
                                MachineHandle=self.node.handle,
                                StateEnum=HpBossState.enum_name(),
                                State=self.state,
                                UnixMs=int(time.time() * 1000)
                            ))
                asyncio.create_task(self._waiting_to_turn_on())
            else:
                self.close_hp_scada_ops_relay()

    def process_sieg_loop_ready(self, from_node: ShNode, payload: SiegLoopReady):
        if self.state == HpBossState.PreparingToTurnOn:
            self.state = HpBossState.HpOn
            self.close_hp_scada_ops_relay()
            self.log(f"Got SiegLoop ready. Changing state to {self.state}")
            self._send_to(self.primary_scada,
                            SingleMachineState(
                                MachineHandle=self.node.handle,
                                StateEnum=HpBossState.enum_name(),
                                State=self.state,
                                UnixMs=int(time.time() * 1000)
                            ))
        # TODO: name/cancelany waiting_to_turn_on task

    async def _waiting_to_turn_on(self)-> None:
        await asyncio.sleep(120)
        # If still in state WaitingToTurnOn, turn on:
        if self.state == HpBossState.PreparingToTurnOn:
            self.state = HpBossState.HpOn
            self.close_hp_scada_ops_relay()
            self.log(f"Did not hear from Sieg loop for 2 moinutes. Turning on anyway!")
            self._send_to(self.primary_scada,
                            SingleMachineState(
                                MachineHandle=self.node.handle,
                                StateEnum=HpBossState.enum_name(),
                                State=self.state,
                                UnixMs=int(time.time() * 1000)
                            ))

    def open_hp_scada_ops_relay(self) -> None:
        try:
            event = FsmEvent(
                FromHandle=self.node.handle,
                ToHandle=self.hp_scada_ops_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.hp_scada_ops_relay, event)
            self.log(f"{self.node.handle} sending OpenRelay to {self.hp_scada_ops_relay.handle}")
        
        except Exception as e:
            self.log(f"Tried to turn off heat pump! {e}")

    def close_hp_scada_ops_relay(self) -> None:
        try:
            event = FsmEvent(
                FromHandle=self.node.handle,
                ToHandle=self.hp_scada_ops_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.CloseRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.hp_scada_ops_relay, event)
            self.log(f"{self.node.handle} sending CloseRelay to {self.hp_scada_ops_relay.handle}")
        
        except Exception as e:
            self.log(f"Tried to turn on heat pump! {e}")

