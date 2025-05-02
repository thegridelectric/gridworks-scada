import time
import uuid
import asyncio
from data_classes.house_0_names import H0CN, H0N
from gwproto.message import Message
from gwproactor import AppInterface
from gwproto.data_classes.sh_node import ShNode
from gwproto.named_types import FsmFullReport
from gwproto.enums import ChangeRelayState
from result import Ok, Result

from actors.scada_actor import ScadaActor
from enums import LogLevel, TurnHpOnOff
from named_types import FsmEvent, Glitch, StratBossReady
    

class HpRelayBoss(ScadaActor):
    TURN_ON_ANYWAY_S = 120 # turn on the heat pump after 2 minutes without strat-boss
    def __init__(self, name: str, services: AppInterface):
        super().__init__(name, services)
        self.hp_model = self.settings.hp_model # TODO: will move to hardware layout
        self.waiting_for_strat_boss: bool = False
        self.last_cmd_time = 0

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
            case FsmEvent():
                try:
                    self.process_fsm_event(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_fsm_event: {e}")
            case FsmFullReport():
                ... # relay reports back with ack of change if we care
            case StratBossReady():
                try:
                    self.process_strat_boss_ready(from_node, payload)
                except Exception as e:
                   self.log(f"Trouble with process_strat_boss_ready: {e}")
            case _: 
                self.log(f"{self.name} received unexpected message: {message.Header}"
            )
        return Ok(True)
    
    
    def process_fsm_event(self, from_node: ShNode, payload: FsmEvent) -> None:    
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
        if payload.EventName == TurnHpOnOff.TurnOn:
            if self.strat_boss_sidelined():
                self.waiting_for_strat_boss = False
                self.close_hp_scada_ops_relay()
            else:
                self.waiting_for_strat_boss = True 
                self._send_to(self.strat_boss, payload)
                self.log("Waiting for StratBossReady before closing relay!")
                asyncio.create_task(self._wait_and_turn_on_anyway())
                # TODO Add timer to raise concern if we haven't heard for a while (message dropped)
                
        else:
            self.waiting_for_strat_boss = False
            self.open_hp_scada_ops_relay()
            if not self.strat_boss_sidelined():
                self._send_to(self.strat_boss, payload)

    async def _wait_and_turn_on_anyway(self) -> None:
        await asyncio.sleep(self.TURN_ON_ANYWAY_S)
        # This is not a good idea. If we transition from home alone
        # to atomic ally, this will turn on the heat pump even if
        # atomic ally doesn't want it.
        # TODO: think more about this
        # if not self.hp_relay_closed():
        #     self.close_hp_scada_ops_relay()

    def process_strat_boss_ready(self, from_node: ShNode, payload: StratBossReady) -> None:
        if self.waiting_for_strat_boss:
            self.log("Strat boss ready received! Closing relay")
            self.close_hp_scada_ops_relay()
            self.waiting_for_strat_boss = False
        else:
            self.log(" That's funny ... StratBossReady received but not waiting for strat boss. Ignoring")

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

    def strat_boss_sidelined(self) -> bool:
        """ Sidelined if it is out of the chain of command; e.g boss is own ShNode"""
        if self.strat_boss.Handle == self.strat_boss.Name:  # not in the command tree, not tracking anytnig
            return True
        return False
        

