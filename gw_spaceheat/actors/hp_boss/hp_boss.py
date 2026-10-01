"""HpBoss: the heat pump's command node in every layout, owning the call
relay and the turn-on strategy. The sensing side of the heat pump is
`sensing.py` beside this file."""

import asyncio
import time
import uuid
from typing import Optional

from gwproto.message import Message
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import (
    ChangeRelayState,
    FsmReportType,
    HpBossState,
    ScadaCmdRefusalReason,
    SiegLoopStrategy,
    TurnHpOnOff,
)
from gwsproto.named_types import (
    DispatchAck,
    DispatchNack,
    FsmAtomicReport,
    FsmEvent,
    FsmFullReport,
    SingleMachineState,
)
from result import Ok, Result

from actors import command_reply
from actors.sh_node_actor import ShNodeActor
from actors.sieg_loop.strategy import SiegLoopReady, selected_strategy
from scada_app_interface import ScadaAppInterface


class HpBoss(ShNodeActor):
    """
    Direct Reports:
    HpBoss
        ├── HpScadaOps
        └── SiegLoop

    Every command to the call relay rides under one TriggerId: the boss's
    when a TurnHpOnOff command drives it, one hp-boss mints when it acts on
    its own (boot, the start timeout). hp-boss keeps its own transitions
    under that id as atomics, folds the relay's full report in when it
    arrives, and sends the one full report to the scada.
    """
    TURN_ON_ANYWAY_S = 120 # turn on the heat pump after 2 minutes without strat-boss
    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self.last_cmd_time = 0
        # The call relay is open at boot (the relay actor adopts the pin, and
        # a de-energized call relay is the failsafe), so the boss starts
        # HpOff: a boss that believed HpOn here would treat the first TurnOn
        # as already done and never close the relay.
        self.state = HpBossState.HpOff
        # The command in flight: its id and hp-boss's own transitions under
        # it, reported in full once the relay's report folds in.
        self.trigger_id: Optional[str] = None
        self.fsm_reports: list[FsmAtomicReport] = []

    def start(self) -> None:
        """Boots the call relay open and reports HpOff, so the relay holds
        the posture the boss believes and the scada's latest-state list
        carries hp-boss from the first snapshot."""
        self.begin(str(uuid.uuid4()))
        self.open_hp_scada_ops_relay()
        self.report_state()

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
                self.process_fsm_full_report(from_node, payload)
            case DispatchAck():
                pass  # the relay took the command; its full report confirms it
            case DispatchNack():
                self.send_error(
                    "relay_nack",
                    f"{from_node.name} refused {payload.TriggerId}: {payload.Reason}",
                )
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
            self.log(f"Handle is {self.node.Handle}; ignoring {payload}")
            self._send_to(
                from_node,
                command_reply.nack(
                    self.node.handle, payload.FromHandle, payload.TriggerId,
                    ScadaCmdRefusalReason.NotMyBoss,
                ),
            )
            return
        if from_node.handle != payload.FromHandle:
            self.send_warning(
                "bad_sender",
                f"{from_node.name} (handle {from_node.handle}) sent a command claiming "
                f"FromHandle {payload.FromHandle}. Ignoring!",
            )
            return
        # TODO: add way for boss to realize its command was ignored before
        # adding the following
        # if time.time() - self.last_cmd_time < 0.5:
        #     self.log("IGNORING COMMAND ")
        if (
            payload.EventType != TurnHpOnOff.enum_name()
            or payload.EventName not in TurnHpOnOff.values()
        ):
            self.log(f"Only listens to {TurnHpOnOff.enum_name()}; refusing {payload}")
            self._send_to(
                from_node,
                command_reply.nack(
                    self.node.handle, payload.FromHandle, payload.TriggerId,
                    ScadaCmdRefusalReason.UnknownEvent,
                ),
            )
            return
        self._send_to(
            from_node,
            command_reply.ack(self.node.handle, payload.FromHandle, payload.TriggerId),
        )
        # No actuators-ready gate: the relay actor defers a command until
        # its boot adoption completes and retries it through the verify
        # loop, and the scada's ActuatorsReady only fires on layouts that
        # carry the Krida multiplexers. Goes with the board-generic
        # required-actuator set when the Krida assumption is removed.
        if payload.EventName == TurnHpOnOff.TurnOff:
            self.begin(payload.TriggerId)
            self.open_hp_scada_ops_relay()
            self.transition(HpBossState.HpOff, TurnHpOnOff.TurnOff)
        elif self.state == HpBossState.HpOff:
            self.begin(payload.TriggerId)
            if selected_strategy(self.ops) is SiegLoopStrategy.StratProtect:
                # The loop protects the start: HpOff -> PreparingToTurnOn;
                # the relay closes when the loop reports ready.
                self.transition(HpBossState.PreparingToTurnOn, TurnHpOnOff.TurnOn)
                asyncio.create_task(self._waiting_to_turn_on())
            else:
                # No loop, or one that holds full send: close the call relay now.
                self.close_hp_scada_ops_relay()
                self.transition(HpBossState.HpOn, TurnHpOnOff.TurnOn)

    def begin(self, trigger_id: str) -> None:
        """Open a command's record. A record still open loses its report."""
        if self.trigger_id is not None:
            self.log(f"Command {self.trigger_id} superseded by {trigger_id} before its relay reported")
        self.trigger_id = trigger_id
        self.fsm_reports = []

    def transition(self, to_state: HpBossState, event: Optional[TurnHpOnOff]) -> None:
        """Move to to_state, keep the transition under the command in
        flight (event None when hp-boss acts on its own), and report the
        state."""
        from_state = self.state
        self.state = to_state
        if self.trigger_id is not None:
            self.fsm_reports.append(
                FsmAtomicReport(
                    MachineHandle=self.node.handle,
                    StateEnum=HpBossState.enum_name(),
                    ReportType=FsmReportType.Event,
                    EventEnum=TurnHpOnOff.enum_name() if event is not None else None,
                    Event=event,
                    FromState=from_state,
                    ToState=to_state,
                    UnixTimeMs=int(time.time() * 1000),
                    TriggerId=self.trigger_id,
                )
            )
        self.report_state()

    def process_fsm_full_report(self, from_node: ShNode, payload: FsmFullReport) -> None:
        """The relay's report under the command in flight folds into
        hp-boss's own, which then goes to the scada."""
        if from_node.Name != self.layout.hp_scada_ops_relay.Name:
            self.log(f"Ignoring fsm.full.report from {from_node.name}")
            return
        if payload.TriggerId != self.trigger_id:
            self.log(f"Ignoring relay report {payload.TriggerId} (command in flight is {self.trigger_id})")
            return
        self._send_to(
            self.primary_scada,
            FsmFullReport(
                FromName=self.name,
                TriggerId=payload.TriggerId,
                AtomicList=[*self.fsm_reports, *payload.AtomicList],
            ),
        )
        self.trigger_id = None
        self.fsm_reports = []

    def report_state(self) -> None:
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=HpBossState.enum_name(),
                State=self.state,
                UnixMs=int(time.time() * 1000),
            ),
        )

    def process_sieg_loop_ready(self, from_node: ShNode, payload: SiegLoopReady):
        self.log(f"Got SiegLoop ready, state is {self.state}")
        if self.state == HpBossState.PreparingToTurnOn:
            self.close_hp_scada_ops_relay()
            self.transition(HpBossState.HpOn, TurnHpOnOff.TurnOn)
            self.log(f"Got SiegLoop ready. Changing state to {self.state}")
        # TODO: name/cancelany waiting_to_turn_on task

    async def _waiting_to_turn_on(self)-> None:
        await asyncio.sleep(120)
        # If still in state WaitingToTurnOn, turn on:
        if self.state == HpBossState.PreparingToTurnOn:
            self.begin(str(uuid.uuid4()))
            self.open_hp_scada_ops_relay()
            self.transition(HpBossState.HpOff, None)
            self.log("Did not hear from Sieg loop for 2 minutes. Turning off!")
            self.alert(
                "Sieg loop did not report ready within 2 minutes",
                "Turning off the heat pump (opened HP scada ops relay).",
            )

    def command_relay(self, event_name: ChangeRelayState) -> None:
        assert self.trigger_id is not None, "a relay command needs a command in flight"
        try:
            event = FsmEvent(
                FromHandle=self.node.handle,
                ToHandle=self.layout.hp_scada_ops_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=event_name,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=self.trigger_id,
            )
            self._send_to(self.layout.hp_scada_ops_relay, event)
            self.log(f"{self.node.handle} sending {event_name} to {self.layout.hp_scada_ops_relay.handle}")
        except Exception as e:
            self.log(f"Tried to command the call relay {event_name}: {e}")

    def open_hp_scada_ops_relay(self) -> None:
        self.command_relay(ChangeRelayState.OpenRelay)

    def close_hp_scada_ops_relay(self) -> None:
        self.command_relay(ChangeRelayState.CloseRelay)
