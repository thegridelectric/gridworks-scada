"""five-v-boss: the hold on the picos' 5 V supply, a command node under
the tree's root in every layout. At rest the pico-cycler owns vdc-relay
under it and five-v-boss forwards RebootPicos; while the 5 V is held off
five-v-boss owns the relay directly and the cycler is a dormant leaf, so a
board can be worked on with the picos dark and brought back without a
reboot cycle. The cycler's own machine is untouched.
"""

import time
import uuid
from typing import Optional

from gwproto.message import Message
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import (
    ChangeRelayState,
    FiveVBossState,
    FsmReportType,
    GwScadaCmdRefusalReason,
    RebootPicos,
    RelayClosedOrOpen,
    Turn5VOnOff,
)
from gwsproto.named_types import (
    DispatchAck,
    DispatchNack,
    FsmAtomicReport,
    FsmEvent,
    FsmFullReport,
    GoDormant,
    SingleMachineState,
    WakeUp,
)
from result import Ok, Result

from actors import command_reply
from actors.command_node import CommandNode
from scada_app_interface import ScadaAppInterface


OFF_PATH = (FiveVBossState.TurningOff, FiveVBossState.FiveVOff)
"""The states the TurnOff command walks; its atomic reports carry TurnOff,
the TurnOn command's carry TurnOn (the vocabulary has no confirmation
event, so a half's label is the command that caused it)."""


def shape_five_v_subtree(layout: HydronicLayout, state: FiveVBossState) -> None:
    """The one funnel for the handles under five-v-boss: the cycler owns
    vdc-relay while the boss rests in PicoCycler; in every other state the
    boss owns the relay and the cycler is a leaf. The scada uses it on a
    tree rewrite (from the boss's last reported state) and the boss on its
    own transitions, so the shape is never written twice."""
    boss = layout.node(H0N.five_v_boss)
    cycler = layout.pico_cycler
    relay = layout.vdc_relay
    cycler.Handle = f"{boss.handle}.{cycler.Name}"
    if state == FiveVBossState.PicoCycler:
        relay.Handle = f"{cycler.Handle}.{relay.Name}"
    else:
        relay.Handle = f"{boss.handle}.{relay.Name}"


class FiveVBoss(CommandNode):
    """
    Direct reports, by state:
        PicoCycler:            five-v-boss ── pico-cycler ── vdc-relay
        TurningOff / FiveVOff / TurningOn:
                               five-v-boss ── pico-cycler   (dormant leaf)
                                          └── vdc-relay
    """

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self.state = FiveVBossState.PicoCycler
        # The commander of each RebootPicos forwarded to the cycler, by the
        # command's TriggerId, so the cycler's reply goes back to whoever asked.
        self.forwarded: dict[str, ShNode] = {}
        # The hold in flight: its TriggerId (the command's, or self-minted on
        # a wake.up) and the atomic reports gathered under it.
        self.trigger_id: Optional[str] = None
        self.fsm_reports: list[FsmAtomicReport] = []

    def start(self) -> None:
        """Reports the boot state so the scada's latest-state list carries
        five-v-boss from the first snapshot."""
        self.report_state()

    def stop(self) -> None:
        ...

    async def join(self) -> None:
        ...

    @property
    def cycler(self) -> ShNode:
        return self.layout.pico_cycler

    @property
    def relay(self) -> ShNode:
        return self.layout.vdc_relay

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        from_node = self.layout.node(message.Header.Src, None)
        if from_node is None:
            return Ok(False)
        payload = message.Payload
        match payload:
            case FsmEvent():
                self.process_fsm_event(from_node, payload)
            case DispatchAck() | DispatchNack():
                self.process_cycler_reply(from_node, payload)
            case FsmFullReport():
                self.process_fsm_full_report(from_node, payload)
            case WakeUp():
                self.wake_up()
            case _:
                self.log(f"{self.name} received unexpected message: {message.Header}")
        return Ok(True)

    # ------------------------------------------------------------------
    # Commands from the boss
    # ------------------------------------------------------------------

    def process_fsm_event(self, from_node: ShNode, payload: FsmEvent) -> None:
        if payload.ToHandle != self.node.handle:
            self.log(f"Handle is {self.node.handle}; refusing {payload.FromHandle} -> {payload.ToHandle}")
            self.refuse(from_node, payload, GwScadaCmdRefusalReason.NotMyBoss)
            return
        if payload.EventType == RebootPicos.enum_name() and payload.EventName in RebootPicos.values():
            self.process_reboot_picos(from_node, payload)
            return
        if payload.EventType != Turn5VOnOff.enum_name() or payload.EventName not in Turn5VOnOff.values():
            self.log(
                f"Takes {Turn5VOnOff.enum_name()} and {RebootPicos.enum_name()}; "
                f"refusing {payload.EventType} {payload.EventName}"
            )
            self.refuse(from_node, payload, GwScadaCmdRefusalReason.UnknownEvent)
            return
        if payload.EventName == Turn5VOnOff.TurnOff:
            self.process_turn_off(from_node, payload)
        else:
            self.process_turn_on(from_node, payload)

    def process_reboot_picos(self, from_node: ShNode, payload: FsmEvent) -> None:
        """Forwarded to the cycler as its boss under the command's own
        TriggerId; the cycler's ack or nack is passed back."""
        if self.state != FiveVBossState.PicoCycler:
            self.refuse(from_node, payload, GwScadaCmdRefusalReason.Busy)
            return
        self.forwarded[payload.TriggerId] = from_node
        self._send_to(
            self.cycler,
            FsmEvent(
                FromHandle=self.node.handle,
                ToHandle=self.cycler.handle,
                EventType=RebootPicos.enum_name(),
                EventName=payload.EventName,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=payload.TriggerId,
            ),
        )
        self.log(f"Forwarded {payload.EventName} from {payload.FromHandle} to {self.cycler.handle}")

    def process_cycler_reply(self, from_node: ShNode, payload: DispatchAck | DispatchNack) -> None:
        commander = self.forwarded.pop(payload.TriggerId, None)
        if from_node.Name != self.cycler.Name or commander is None:
            self.log(f"Ignoring reply {payload.TriggerId} from {from_node.name}")
            return
        reply = payload.model_copy(update={"FromHandle": self.node.handle, "ToHandle": commander.handle})
        self._send_to(commander, reply)

    def process_turn_off(self, from_node: ShNode, payload: FsmEvent) -> None:
        if self.state != FiveVBossState.PicoCycler or not self.relay_reported_closed():
            self.refuse(from_node, payload, GwScadaCmdRefusalReason.Busy)
            return
        self._send_to(
            from_node,
            command_reply.ack(self.node.handle, payload.FromHandle, payload.TriggerId),
        )
        self.turn_off(payload.TriggerId)

    def process_turn_on(self, from_node: ShNode, payload: FsmEvent) -> None:
        if self.state in (FiveVBossState.TurningOff, FiveVBossState.TurningOn):
            self.refuse(from_node, payload, GwScadaCmdRefusalReason.Busy)
            return
        self._send_to(
            from_node,
            command_reply.ack(self.node.handle, payload.FromHandle, payload.TriggerId),
        )
        if self.state == FiveVBossState.FiveVOff:
            self.turn_on(payload.TriggerId)

    def refuse(self, from_node: ShNode, payload: FsmEvent, reason: GwScadaCmdRefusalReason) -> None:
        self._send_to(
            from_node,
            command_reply.nack(self.node.handle, payload.FromHandle, payload.TriggerId, reason),
        )

    def relay_reported_closed(self) -> bool:
        """The relay's last reported state, off the scada's latest-state
        list: closed also means the cycler is not mid-cycle."""
        latest = self.data.latest_machine_state.get(self.relay.Name)
        return latest is not None and latest.State == RelayClosedOrOpen.RelayClosed

    # ------------------------------------------------------------------
    # The hold
    # ------------------------------------------------------------------

    def turn_off(self, trigger_id: str) -> None:
        """PicoCycler -> TurningOff: the cycler goes dormant, the relay
        moves under five-v-boss, and the open goes out under the hold's id."""
        self.trigger_id = trigger_id
        self.fsm_reports = []
        self._send_to(self.cycler, GoDormant(ToName=self.cycler.Name))
        self.transition(FiveVBossState.TurningOff)
        shape_five_v_subtree(self.layout, self.state)
        self.publish_command_tree()
        self.command_relay(ChangeRelayState.OpenRelay)

    def turn_on(self, trigger_id: str) -> None:
        """FiveVOff / TurningOff -> TurningOn: the close goes out; the relay
        is handed back to the cycler on its closed confirmation."""
        self.trigger_id = trigger_id
        self.fsm_reports = []
        self.transition(FiveVBossState.TurningOn)
        self.command_relay(ChangeRelayState.CloseRelay)

    def wake_up(self) -> None:
        """The scada's AutoWakesUp (admin release or timeout): restore the
        5 V under a self-minted id, so LocalControl never inherits a dark
        fleet. Ignored while the picos are already powered."""
        if self.state in (FiveVBossState.FiveVOff, FiveVBossState.TurningOff):
            self.log(f"wake.up in {self.state}: restoring the 5 V")
            self.turn_on(str(uuid.uuid4()))
        else:
            self.log(f"wake.up in {self.state}: nothing to restore")

    def process_fsm_full_report(self, from_node: ShNode, payload: FsmFullReport) -> None:
        if from_node.Name != self.relay.Name:
            self.log(f"Ignoring fsm.full.report from {from_node.name}")
            return
        if payload.TriggerId != self.trigger_id:
            self.log(f"Ignoring relay report {payload.TriggerId} (hold is {self.trigger_id})")
            return
        event = payload.AtomicList[0].Event
        if event == ChangeRelayState.OpenRelay and self.state == FiveVBossState.TurningOff:
            self.transition(FiveVBossState.FiveVOff)
            self.send_fsm_report()
        elif event == ChangeRelayState.CloseRelay and self.state == FiveVBossState.TurningOn:
            self.transition(FiveVBossState.PicoCycler)
            shape_five_v_subtree(self.layout, self.state)
            self.publish_command_tree()
            self._send_to(self.cycler, WakeUp(ToName=self.cycler.Name))
            self.send_fsm_report()
        else:
            self.log(f"Ignoring relay {event} confirmation in {self.state}")

    def command_relay(self, event_name: ChangeRelayState) -> None:
        self._send_to(
            self.relay,
            FsmEvent(
                FromHandle=self.node.handle,
                ToHandle=self.relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=event_name,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=self.trigger_id,
            ),
        )
        self.log(f"{event_name} to {self.relay.handle}")

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def transition(self, to_state: FiveVBossState) -> None:
        from_state = self.state
        self.state = to_state
        self.fsm_reports.append(
            FsmAtomicReport(
                MachineHandle=self.node.handle,
                StateEnum=FiveVBossState.enum_name(),
                ReportType=FsmReportType.Event,
                EventEnum=Turn5VOnOff.enum_name(),
                Event=Turn5VOnOff.TurnOff if to_state in OFF_PATH else Turn5VOnOff.TurnOn,
                FromState=from_state,
                ToState=to_state,
                UnixTimeMs=int(time.time() * 1000),
                TriggerId=self.trigger_id,
            )
        )
        self.report_state()
        self.log(f"{from_state} -> {to_state}")

    def send_fsm_report(self) -> None:
        """One half of the hold is complete (off: PicoCycler -> FiveVOff; on:
        FiveVOff -> PicoCycler); the journal gets it under the hold's id."""
        self._send_to(
            self.primary_scada,
            FsmFullReport(
                FromName=self.name,
                TriggerId=self.trigger_id,
                AtomicList=self.fsm_reports,
            ),
        )
        self.fsm_reports = []
        self.trigger_id = None

    def report_state(self) -> None:
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=FiveVBossState.enum_name(),
                State=self.state,
                UnixMs=int(time.time() * 1000),
            ),
        )
