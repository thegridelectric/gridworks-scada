import asyncio
import time
import uuid
from typing import Dict, List, Optional, Sequence
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import (
    ChangeRelayState,
    FsmReportType,
    RebootPicos,
)
from gwsproto.named_types import (
    ChannelReadings,
    FsmAtomicReport,
    FsmEvent,
    FsmFullReport,
    MachineStates,
    SyncedReadings,
)
from result import Ok, Result
from transitions import Machine
import transitions
from actors.hydronic.shared import HydronicNode
from actors import command_reply
from gwsproto.enums import (
    GwScadaCmdRefusalReason,
    LogLevel,
    PicoCyclerEvent,
    PicoCyclerState,
    SinglePicoState,
)
from gwsproto.named_types import Glitch, GoDormant, PicoMissing, WakeUp
from gwsproto.data_classes.components import (
    PicoBtuMeterComponent,
    PicoFlowModuleComponent,
    PicoTankModuleComponent,
    SimPicoTankModuleComponent,
)

from scada_app_interface import ScadaAppInterface
class PicoWarning(ValueError):
    pico_name: str

    def __init__(self, *, msg: str = "", pico_name:str):
        self.pico_name = pico_name
        super().__init__(msg)

    def __str__(self):
        return f"PicoWarning: {self.pico_name}  <{super().__str__()}>"

class ZombiePicoWarning(PicoWarning):

    def __str__(self):
        return f"ZombiePicoWarning: {self.pico_name}  <{super().__str__()}>"

class PicoCycler(HydronicNode):
    REBOOT_ATTEMPTS = 3
    RELAY_OPEN_S: float = 5
    PICO_REBOOT_S = 60
    STATE_REPORT_S = 300
    ZOMBIE_UPDATE_HR = 1
    SHAKE_ZOMBIE_HR = 0.5
    actor_by_pico: Dict[str, ShNode]
    pico_actors: List[ShNode]
    pico_states: Dict[str, SinglePicoState]
    pico_relay: ShNode
    trigger_id: Optional[str]
    fsm_reports: List[FsmAtomicReport]
    _stop_requested: bool

    states = [
        "Dormant",
        "PicosLive",
        "RelayOpening",
        "RelayOpen",
        "RelayClosing",
        "PicosRebooting",
        "AllZombies",
    ]
    transitions = [
        {"trigger": "PicoMissing", "source": "PicosLive", "dest": "RelayOpening"},
        {"trigger": "ConfirmOpened", "source": "RelayOpening", "dest": "RelayOpen"},
        {"trigger": "StartClosing", "source": "RelayOpen", "dest": "RelayClosing"},
        {
            "trigger": "ConfirmClosed",
            "source": "RelayClosing",
            "dest": "PicosRebooting",
        },
        {"trigger": "ConfirmRebooted", "source": "PicosRebooting", "dest": "PicosLive"},
        {"trigger": "PicoMissing", "source": "PicosRebooting", "dest": "RelayOpening"},
        {"trigger": "RebootDud", "source": "PicosRebooting", "dest": "AllZombies"},
        {"trigger": "ShakeZombies", "source": "AllZombies", "dest": "RelayOpening"},
        {"trigger": "ShakeZombies", "source": "PicosLive", "dest": "RelayOpening"},
        {"trigger": "Startup", "source": "PicosLive", "dest": "RelayOpening"},
    ] + [ 
        {"trigger": "GoDormant", "source": state, "dest": "Dormant"}
        for state in states if state !="Dormant"
    ] + [{"trigger":"WakeUp","source": "Dormant", "dest": "PicosLive"}]
    

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self.pico_relay = self.layout.vdc_relay

        # ---------------------------------------------------------
        # Discover Pico-backed actors
        # ---------------------------------------------------------
        self.pico_actors: list[ShNode] = []
        self.actor_by_pico: dict[str, ShNode] = {}
        self.picos: list[str] = [] # list of hw_uids

        for node in self.layout.nodes.values():

            # 1. Skip nodes with no component entirely
            component = getattr(node, "component", None)
            if component is None:
                continue

            if isinstance(component, PicoBtuMeterComponent):
                hw_uid = component.gt.HwUid
            elif isinstance(component, PicoFlowModuleComponent):
                hw_uid = component.gt.HwUid
            elif isinstance(component, (PicoTankModuleComponent, SimPicoTankModuleComponent)):
                hw_uid = component.gt.PicoHwUid
            else:
                continue
            if hw_uid is None:
                self.send_warning(
                    "Pico without HwUid",
                    f"{node.name} of class {node.actor_class} missing HwUid!")
                continue

            if hw_uid in self.actor_by_pico:
                raise ValueError(f"Duplicate pico hw_uid {hw_uid} for nodes {self.actor_by_pico[hw_uid].name} and {node.name}")
            self.actor_by_pico[hw_uid] = node
            self.pico_actors.append(node)
            self.picos.append(hw_uid)

        self.pico_by_actor = {actor: pico for pico, actor in self.actor_by_pico.items()}

        self.last_open_time = time.time() # used to track how long since the VDC relay was cycled
        self._stop_requested = False
                    
        if not self.pico_actors:
            self.log("PicoCycler initialized with no Pico-backed actors")
        self.pico_states = {pico: SinglePicoState.Alive for pico in self.picos}
        # This counts consecutive failed reboots per pico
        self.reboots = {pico: 0 for pico in self.picos}
        self.trigger_id = None
        self.fsm_comment = None
        self.fsm_reports = []
        self.last_zombie_problem_report_s = time.time() - 24 * 3600
        self.last_zombie_shake = time.time()
        self.state = PicoCyclerState.PicosLive
        self.machine = Machine(
            model=self,
            states=PicoCycler.states,
            transitions=PicoCycler.transitions,
            initial=PicoCyclerState.PicosLive,
            send_event=True,
        )

    @property
    def flatlined(self) -> List[str]:
        """
        Non-zombie picos that have not been sending messages recently
        """
        non_zombies = [pico for pico in self.picos if pico not in self.zombies]
        flatlined = []
        for pico in non_zombies:
            if self.pico_states[pico] == SinglePicoState.Flatlined:
                flatlined.append(pico)
        return flatlined

    @property
    def zombies(self) -> List[str]:
        """
        Picos that we are supposed to be tracking that have been
        gone for too many consecutive reboots (REBOOT ATTEMPTS)
        """
        zombies = []
        for pico in self.picos:
            if self.reboots[pico] >= self.REBOOT_ATTEMPTS:
                zombies.append(pico)
        return zombies

    @property
    def all_zombies(self) -> bool:
        if len(self.zombies) == len(self.picos):
            return True
        return False

    def pico_state(self, pico: str) -> SinglePicoState:
        """The pico's state as reported: Zombie once its consecutive failed
        reboots reach the threshold, else what its readings say."""
        if pico in self.zombies:
            return SinglePicoState.Zombie
        return self.pico_states[pico]

    def report_pico_state(self, pico: str, now_ms: Optional[int] = None) -> None:
        """One machine.states row for this pico, keyed by its actor's handle,
        so the journal carries the roster and a cycle reads against the pico
        whose row flipped just before it."""
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        self._send_to(
            self.primary_scada,
            MachineStates(
                MachineHandle=self.actor_by_pico[pico].handle,
                StateEnum=SinglePicoState.enum_name(),
                StateList=[self.pico_state(pico)],
                UnixMsList=[now_ms],
            ),
        )

    def report_pico_roster(self) -> None:
        now_ms = int(time.time() * 1000)
        for pico in self.picos:
            self.report_pico_state(pico, now_ms)

    def raise_zombie_pico_warning(self, pico: str) -> None:
        if pico not in self.actor_by_pico:
            raise Exception(
                f"Expect {pico} to be in self.actor_by_pico {self.actor_by_pico}!"
            )
        if self.reboots[pico] < self.REBOOT_ATTEMPTS:
            raise Exception(
                f"{pico} is not a zombie, should not be in raise_zombie_pico_warning!"
            )

        self._send_to(
            self.ltn,
            Glitch(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                Node=self.actor_by_pico[pico].name,
                Type=LogLevel.Info,
                Summary="pico-just-zombied",
                Details=f"Flatlined for more than {self.REBOOT_ATTEMPTS} VDC cycles"
            )
        )

    def process_pico_missing(self, actor: ShNode, payload: PicoMissing) -> None:
        # picos can take 45 seconds to come back after power cycling.
        # So ignore a pico missing message if we've opened the VDC relay 
        # in the last minute
        if time.time() - self.last_open_time < 60:
            return
        expected = self.pico_by_actor.get(actor)
        if expected is None:
            return
        if expected != payload.PicoHwUid:
            self.send_error(
                "Pico Mismatch!",
                f"Got {payload} from {actor.name} but expected {expected}"
            )
        pico = expected
        if actor not in self.pico_actors:
            return
        if pico in self.zombies:
            return
        if self.pico_states[pico] == SinglePicoState.Alive:
            # this pico is now flatlined if it was not before
            self.pico_states[pico] = SinglePicoState.Flatlined
            self.log(f"{actor.name} {pico} flatlined")
            self.report_pico_state(pico)
        
        # move out of PicosLive if pico cycler in that state
        if self.state == PicoCyclerState.PicosLive:
            # this kicks off an fsm report sequence, which requires a comment
            self.trigger_id = str(uuid.uuid4())
            comment=f"triggered by {payload.ActorName} {payload.PicoHwUid}"
            self.fsm_comment = comment
            self.pico_missing()

    def pico_missing(self) -> None:
        """
        Called directly when rebooting picos does not bring back all the
        picos, or indirectly when state is PicosLive and we receive a
        PicoMissing message from an actor
        """
        if not self.trigger_event(PicoCyclerEvent.PicoMissing):
            return
        self.log(f"TRIGGERING PICO REBOOT! {self.fsm_comment}")
        # increment reboot attempts for all flatlined picos
        for pico in self.pico_states:
            if self.pico_states[pico] == SinglePicoState.Flatlined:
                self.reboots[pico] += 1
                # If this is the first time a pico reaches the zombie threshold,
                # raise that warning
                if self.reboots[pico] == self.REBOOT_ATTEMPTS:
                    self.report_pico_state(pico)
                    self.raise_zombie_pico_warning(pico)
        # Send action on to pico relay
        self.open_vdc_relay(trigger_id=self.trigger_id)

    def process_synced_readings(self, actor: ShNode, payload: SyncedReadings) -> None:
        if actor not in self.pico_actors:
            self.log(
                f"Received SyncedReadings from {actor.name}, not a Pico-backed actor"
            )
            return

        pico = self.pico_by_actor.get(actor)
        if pico is None:
            raise RuntimeError(
                f"[{self.name}] Pico-backed actor {actor.name} not found in actor_by_pico"
            )

        self.is_alive(pico)

    def process_channel_readings(self, actor: ShNode, payload: ChannelReadings) -> None:
        if actor not in self.pico_actors:
            self.log(
                f"Received ChannelReadings from {actor.name}, not a Pico-backed actor"
            )
            return

        pico = self.pico_by_actor.get(actor)
        if pico is None:
            raise RuntimeError(
                f"[{self.name}] Pico-backed actor {actor.name} not found in actor_by_pico"
            )

        self.is_alive(pico)

    def is_alive(self, pico: str) -> None:
        was_zombie = pico in self.zombies
        was = self.pico_state(pico)

        self.pico_states[pico] = SinglePicoState.Alive
        self.reboots[pico] = 0
        if was != SinglePicoState.Alive:
            self.report_pico_state(pico)

        if was_zombie:
            note = f"Pico {pico} [{self.actor_by_pico[pico].name}] recovered from zombie state"
            self.log(note)
            self.send_info(f"Zombie {self.actor_by_pico[pico].name} recovered!", note)

        if self.state == PicoCyclerState.PicosRebooting and self.flatlined == []:
            self.confirm_rebooted()

    def confirm_rebooted(self) -> None:
        if self.state == PicoCyclerState.PicosRebooting:
            # ConfirmRebooted: PicosRebooting -> PicosLive
            if self.trigger_event(PicoCyclerEvent.ConfirmRebooted):
                self.send_fsm_report()

    def process_fsm_full_report(self, payload: FsmFullReport) -> None:
        if payload.FromName != self.layout.vdc_relay.name:
            raise Exception(
                f"should only get FsmFullReports from VdcRelay, not {payload.FromName}"
            )
        # start_time = payload.AtomicList[0].UnixTimeMs
        # end_time = payload.AtomicList[-1].UnixTimeMs
        # self.log(f"Relay1 dispatch took {end_time - start_time} ms")
        relay_report = payload.AtomicList[0]
        if relay_report.EventEnum != ChangeRelayState.enum_name():
            raise Exception(
                f"[{self.name}] Expect EventEnum change.relay.state, not {relay_report.EventEnum}"
            )
        if relay_report.Event == ChangeRelayState.OpenRelay:
            self.confirm_opened()
        else:
            self.confirm_closed()

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        # print(f"++pico_cycler  {message.message_type()}", flush=True)
        self.services.logger.path(f"++pico_cycler  {message.message_type()}")
        path_dbg = 0
        src_node = self.layout.node(message.Header.Src)
        if src_node is not None:
            path_dbg |= 0x00000001
            match message.Payload:
                case ChannelReadings():
                    path_dbg |= 0x00000002
                    self.process_channel_readings(src_node, message.Payload)
                case FsmEvent():
                    path_dbg |= 0x00000040
                    self.process_fsm_event(src_node, message.Payload)
                case FsmFullReport():
                    path_dbg |= 0x00000004
                    self.process_fsm_full_report(message.Payload)
                case GoDormant():
                    if self.state != PicoCyclerState.Dormant:
                        self.GoDormant()
                        self.log("Going Dormant!")
                case PicoMissing():
                    path_dbg |= 0x00000008
                    self.process_pico_missing(src_node, message.Payload)
                case SyncedReadings():
                    path_dbg |= 0x00000010
                    self.process_synced_readings(src_node, message.Payload)
                case WakeUp():
                    self.WakeUp()
                case _:
                    path_dbg |= 0x00000020
        self.services.logger.path(f"--pico_cycler  path:0x{path_dbg:08X}")
        return Ok(True)
    
    def WakeUp(self) -> None:
        if self.state == PicoCyclerState.Dormant:
            self.trigger_event(PicoCyclerEvent.WakeUp)
            # WakeUp: Dormant -> PicosLive
            self.log("Waking up and making sure vdc relay is closed!")
            self.close_vdc_relay()
        else:
            self.log(f"Got WakeUp message but ignoring since in state {self.state}")

    def confirm_opened(self):
        if self.state == PicoCyclerState.RelayOpening:
            # ConfirmOpened: RelayOpening -> RelayOpen
            if self.trigger_event(PicoCyclerEvent.ConfirmOpened):
                # The picos lose power here; PicoMissing is expected for
                # the next minute, not a fault.
                self.last_open_time = time.time()
                asyncio.create_task(self._wait_and_close_relay())

    def confirm_closed(self) -> None:
        if self.state == PicoCyclerState.RelayClosing:
            # ConfirmClosed: RelayClosing -> PicosRebooting
            if self.trigger_event(PicoCyclerEvent.ConfirmClosed):
                asyncio.create_task(self._wait_for_rebooting_picos())

    async def _wait_and_close_relay(self) -> None:
        # Wait for RelayOpen_S seconds before closing the relay
        cycle = self.trigger_id
        self.pico_state_log(
            f"Keeping VDC Relay 1 open for {self.RELAY_OPEN_S} seconds"
        )
        await asyncio.sleep(self.RELAY_OPEN_S)
        if self.trigger_id != cycle:
            self.pico_state_log(f"Relay-open wait from cycle {cycle} is stale; ignoring")
            return
        self.start_closing()

    async def _wait_for_rebooting_picos(self) -> None:
        # The wait belongs to the cycle that spawned it: a later cycle in
        # PicosRebooting when this timer fires must not be confirmed by it.
        cycle = self.trigger_id
        self.pico_state_log(
            f"Waiting {self.PICO_REBOOT_S} seconds for picos to come back"
        )
        if self.state != PicoCyclerState.PicosRebooting:
            raise Exception(
                f"Wait and open relay should only happen for PicosRebooting, not {self.state}"
            )
        await asyncio.sleep(self.PICO_REBOOT_S)
        if self.trigger_id != cycle:
            self.pico_state_log(f"Reboot wait from cycle {cycle} is stale; ignoring")
            return
        if self.all_zombies:
            self.reboot_dud()
        elif len(self.flatlined) > 0:
            self.fsm_comment = f"Flatlined picos: {self.flatlined}"
            self.pico_missing()
        else:
            self.confirm_rebooted()

    def reboot_dud(self) -> None:
        if self.trigger_event(PicoCyclerEvent.RebootDud):
            self.send_fsm_report()

    def process_fsm_event(self, from_node: ShNode, message: FsmEvent) -> None:
        """The one command a boss may give: reboot the picos. Accepted only
        from the immediate boss, addressed to this node's live handle, as
        relay.py checks its commander; the cycle adopts the commander's
        TriggerId so its fsm.full.report is tied to the command."""
        if message.FromHandle != from_node.handle:
            self.log(
                f"from_node {from_node.name} has handle {from_node.handle}, not {message.FromHandle}!"
            )
            return
        if message.ToHandle != self.node.handle:
            self._send_to(
                self.ltn,
                Glitch(
                    FromGNodeAlias=self.layout.scada_g_node_alias,
                    Node=self.name,
                    Type=LogLevel.Warning,
                    Summary="bad_boss",
                    Details=f"{message.FromHandle} tried to command {self.node.handle}. Ignoring!",
                ),
            )
            self.log(f"Handle is {self.node.handle}; ignoring {message}")
            return
        if (
            message.EventType != RebootPicos.enum_name()
            or message.EventName not in RebootPicos.values()
        ):
            self.log(
                f"Refusing {message.EventType} {message.EventName}: the pico-cycler takes only {RebootPicos.enum_name()}"
            )
            self._send_to(
                from_node,
                command_reply.nack(
                    self.node.handle, message.FromHandle, message.TriggerId,
                    GwScadaCmdRefusalReason.UnknownEvent,
                ),
            )
            return
        if self.state not in {PicoCyclerState.PicosLive, PicoCyclerState.AllZombies}:
            self.log(f"State is {self.state} so not rebooting picos on command")
            self._send_to(
                from_node,
                command_reply.nack(
                    self.node.handle, message.FromHandle, message.TriggerId,
                    GwScadaCmdRefusalReason.Busy,
                ),
            )
            return
        self.trigger_id = message.TriggerId
        self.fsm_comment = f"{message.EventName} commanded by {message.FromHandle}"
        # ShakeZombies: AllZombies/PicosLive -> RelayOpening
        if self.trigger_event(PicoCyclerEvent.ShakeZombies):
            self._send_to(
                from_node,
                command_reply.ack(self.node.handle, message.FromHandle, message.TriggerId),
            )
            self.log(f"TRIGGERING PICO REBOOT! {self.fsm_comment}")
            self.open_vdc_relay(self.trigger_id)

    def startup(self) -> None:
        """The boot-time cycle: every pico is power-cycled once so the roster
        starts from a known state. Enters through Startup, not PicoMissing,
        so the journal does not record a pico missing that never was."""
        self.trigger_id = str(uuid.uuid4())
        self.fsm_comment = "startup"
        # Startup: PicosLive -> RelayOpening
        if self.trigger_event(PicoCyclerEvent.Startup):
            self.log(f"TRIGGERING PICO REBOOT! {self.fsm_comment}")
            self.open_vdc_relay(self.trigger_id)

    def shake_zombies(self) -> None:
        self.last_zombie_shake = time.time()
        if self.state not in {PicoCyclerState.PicosLive, PicoCyclerState.AllZombies}:
            self.log(f"State is {self.state} so not shaking zombies")
            return
        zombies = []
        for pico in self.zombies:
            zombies.append(f" {pico} [{self.actor_by_pico[pico].name}], reboots: {self.reboots[pico]}")
        if len(zombies) > 0:
            self.log(f"Shaking these zombies: {self.zombies}")
            self.trigger_id = str(uuid.uuid4())
            # ShakeZombies: AllZombies/PicosLive -> RelayOpening
            self.trigger_event(PicoCyclerEvent.ShakeZombies)
            self.open_vdc_relay(self.trigger_id)

    def start_closing(self) -> None:
        # Transition to RelayClosing and send CloseRelayCmd
        if self.state == PicoCyclerState.RelayOpen:
            # StartCLosing: RelayOpen -> RelayClosing
            if self.trigger_event(PicoCyclerEvent.StartClosing):
                # Send action on to pico relay
                self.close_vdc_relay(self.trigger_id)

    def send_fsm_report(self) -> None:
        # This is the end of a triggered cycle, so send  FsmFullReport to SCADA
        # and flush trigger_id and fsm_reports
        self._send_to(
            self.primary_scada,
            FsmFullReport(
                FromName=self.name,
                TriggerId=self.trigger_id,
                AtomicList=self.fsm_reports,
            ),
        )
        # self.log(
        #     "Sending report to scada. check "
        #     f"s._data.recent_fsm_reports['{self.trigger_id}']"
        # )
        self.fsm_reports = []
        self.trigger_id = None
        self.fsm_comment = None

    def trigger_event(self, event: PicoCyclerEvent) -> bool:
        now_ms = int(time.time() * 1000)
        orig_state = self.state
        try:
            self.trigger(event)
        except transitions.core.MachineError as e:
            self.log(f"transition failure!: {e}")
            return False
        # Add to fsm reports of linked state changes
        if not self.trigger_id:
            self.trigger_id = str(uuid.uuid4())
        self.fsm_reports.append(
            FsmAtomicReport(
                MachineHandle=self.node.handle,
                StateEnum=PicoCyclerState.enum_name(),
                ReportType=FsmReportType.Event,
                EventEnum=PicoCyclerEvent.enum_name(),
                Event=event,
                FromState=orig_state,
                ToState=self.state,
                UnixTimeMs=now_ms,
                TriggerId=self.trigger_id,
            )
        )
        # update the existing states for scada now
        self._send_to(
            self.primary_scada,
            MachineStates(
                MachineHandle=self.node.handle,
                StateEnum=PicoCyclerState.enum_name(),
                StateList=[self.state],
                UnixMsList=[now_ms],
            ),
        )
        self.pico_state_log(
            f"{event.value}: {orig_state} -> {self.state}"
        )
        return True

    def start(self) -> None:
        self.report_pico_roster()
        self.services.add_task(
            asyncio.create_task(self.main(), name="picocycler keepalive")
        )

    def stop(self) -> None:
        """
        IOLoop will take care of shutting down webserver interaction.
        Here we stop periodic reporting task.
        """
        self._stop_requested = True

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""
        ...

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.STATE_REPORT_S * 2.1)]

    async def main(self) -> None:
        """
        Responsible for sending synchronous state reports and occasional
        zombie notifications
        """
        await asyncio.sleep(3)
        self.startup()

        while not self._stop_requested:
            self.pico_state_log(f"State is {self.state}")
            hiccup = 2.2
            sleep_s = max(
                hiccup, self.STATE_REPORT_S - (time.time() % self.STATE_REPORT_S) - 2
            )
            print(f"[{self.name}] Sleeping for {sleep_s}")
            await asyncio.sleep(sleep_s)
            # report the state
            if sleep_s != hiccup:
                self._send(PatInternalWatchdogMessage(src=self.name))
                self._send_to(
                    self.primary_scada,
                    MachineStates(
                        MachineHandle=self.node.handle,
                        StateEnum=PicoCyclerState.enum_name(),
                        StateList=[self.state],
                        UnixMsList=[int(time.time() * 1000)],
                    ),
                )
                self.report_pico_roster()

            # if all picos are zombies, wifi is probably out.
            # power cycle on a semi-regular basis to get them
            # back when wifi is back
            if time.time() - self.last_zombie_shake > self.SHAKE_ZOMBIE_HR * 3600:
                self.shake_zombies()
            # report the varios zombie picos as problem events
            zombie_update_period = self.ZOMBIE_UPDATE_HR * 3600
            last = self.last_zombie_problem_report_s
            next_zombie_problem = (
                last + zombie_update_period - (last % zombie_update_period)
            )
            zombies = []
            for pico in self.zombies:
                zombies.append(f" {pico} [{self.actor_by_pico[pico].name}]")
            if time.time() > next_zombie_problem and len(zombies) > 0:
                self.log(f"Sending problem event for zombies {zombies}")
                self._send_to(
                    self.ltn,
                    Glitch(
                        FromGNodeAlias=self.layout.scada_g_node_alias,
                        Node=self.node.name,
                        Type=LogLevel.Info,
                        Summary="pico-zombies",
                        Details=",".join(zombies)
                    )
                )
                self.last_zombie_problem_report_s = time.time()

    def pico_state_log(self, note: str) -> None:
        log_str = f"[PicoCyclerState] {note}"
        if self.settings.pico_cycler_state_logging:
            self.services.logger.error(log_str)
    
