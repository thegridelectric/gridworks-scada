"""Implements Relay Actors"""
import asyncio
import time
from typing import Dict, List, NamedTuple, Sequence, Optional

from gwsproto.enums import SemaEnum
from gwproto.message import Message
from gwsproto.data_classes.data_channel import DataChannel
from gwproactor import  MonitoredName
from gwproactor.message import PatInternalWatchdogMessage

from gwsproto.data_classes.components import (
    I2cRelayComponent,
    GpioRelayComponent,
)
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import (
    AquastatControl,
    ChangeAquastatControl,
    ChangeHeatPumpControl,
    ChangePrimaryPumpControl,
    ChangeRelayPin,
    ChangeRelayState,
    ChangeStoreFlowRelay,
    ChangeValveState,
    ChangeZoneCallSource,
    FsmReportType,
    HeatPumpControl,
    PrimaryPumpControl,
    RelayClosedOrOpen,
    RelayPinState,
    RelayWiringConfig,
    StoreFlowRelay,
    ValveOpenOrClosed,
    ZoneCallSource,

)

from gwsproto.named_types import (
    FsmAtomicReport,
    FsmFullReport,
)
from gwsproto.property_format import NonNegativeInt, UTCMilliseconds, UUID4Str
from result import Err, Ok, Result
from transitions import Machine
from actors.sh_node_actor import ShNodeActor
from plant import Heard, RelayDrive
from scada_app_interface import ScadaAppInterface
from gwsproto.enums import LogLevel, ChangeKeepSend, HpLoopKeepSend
from gwsproto.named_types import FsmEvent, Glitch, SingleMachineState, SingleReading
from actors import command_reply
from gwsproto.enums import ScadaCmdRefusalReason
from gwsproto.names.hydronic_spaceheat.node_names import (
    HydronicSpaceheatNodeNames as HSNN,
)
from gwsproto.names.house0.node_names import House0NodeNames

# Internal FSM state before the first pin adoption / confirmation. Never
# published: the state vocabularies carry no Unknown value, and an
# out-of-vocab wire value coerces to the enum default at decode.
UNKNOWN_STATE = "Unknown"

# The control vocabularies an i2c relay's config may declare. The config's
# EventType/StateType (left.right.dot enum names) select the FSM vocabulary —
# layout-driven, no node-name matching.
EVENT_ENUM_BY_NAME: dict[str, type[SemaEnum]] = {
    e.enum_name(): e
    for e in (
        ChangeAquastatControl,
        ChangeHeatPumpControl,
        ChangeKeepSend,
        ChangePrimaryPumpControl,
        ChangeRelayState,
        ChangeStoreFlowRelay,
        ChangeValveState,
        ChangeZoneCallSource,
    )
}
STATE_ENUM_BY_NAME: dict[str, type[SemaEnum]] = {
    s.enum_name(): s
    for s in (
        AquastatControl,
        HeatPumpControl,
        HpLoopKeepSend,
        PrimaryPumpControl,
        RelayClosedOrOpen,
        StoreFlowRelay,
        ValveOpenOrClosed,
        ZoneCallSource,
    )
}


def pin_action(pin_value: int) -> ChangeRelayPin:
    return ChangeRelayPin.Energize if pin_value == 1 else ChangeRelayPin.DeEnergize


def pin_of(position: Optional[ChangeRelayPin]) -> int | None:
    if position is None:
        return None
    return 1 if position == ChangeRelayPin.Energize else 0


class I2cCommand(NamedTuple):
    """A commanded transition not yet confirmed at the pin. Held as the
    relay's enforcement target until confirmation succeeds — the verify loop
    retries it (converge-on-intent, the summer hack's enforce behavior), so a
    transient bus failure heals without the boss re-commanding. A newer
    command supersedes it. pin_value is 1 to energize and 0 to de-energize
    (NonNegativeInt, so not PositiveInt);
    the states/events are values of the config-declared vocabularies."""

    pin_value: NonNegativeInt
    target_state: str
    event_name: str
    relay_pin_event: ChangeRelayPin
    trigger_id: UUID4Str
    boss: ShNode
    send_time_ms: UTCMilliseconds


class Relay(ShNodeActor):
    STATE_REPORT_S = 300
    READY_TIMEOUT_S = 10.0
    # A failed attempt retries on its own at these delays before the verify
    # pass takes over.
    RETRY_BACKOFF_S: tuple[float, ...] = (2.0, 10.0)
    node: ShNode
    wiring_config: RelayWiringConfig
    reports_by_trigger: Dict[str, List[FsmAtomicReport]]
    boss_by_trigger: Dict[str, ShNode]
    energized_state: str
    de_energized_state: str

    def __init__(
        self,
        name: str,
        services: ScadaAppInterface,
    ):
        super().__init__(name, services)

        self._component = self.node.component

        if not isinstance(
            self._component, (I2cRelayComponent, GpioRelayComponent)
        ):
            raise ValueError(f"Component for {self.name} has type "
                             f"{type(self._component)}. Expected "
                             "I2cRelayComponent or GpioRelayComponent")

        self.relay_actor_config = next(
            (x for x in self._component.gt.ConfigList if x.ActorName == self.node.name),
            None,
        )

        if self.relay_actor_config is None:
            raise Exception(
                f"Relay {self.node.name} not in component {self._component}'s ConfigList:\n"
                f"{self._component.gt.ConfigList}"
            )

        self.de_energizing_event = self.relay_actor_config.DeEnergizingEvent
        self.reports_by_trigger = {}
        self.boss_by_trigger = {}
        self.my_event_enum: type[SemaEnum] = ChangeRelayState
        self.my_state_enum: type[SemaEnum] = RelayClosedOrOpen

        self._i2c_command: I2cCommand | None = None
        self._enforce_failing = False
        self._ready = asyncio.Event()
        self.drive = self.my_device(RelayDrive)

        self.initialize_fsm()
        self._stop_requested = False
        if not isinstance(self._component, I2cRelayComponent):
            self.state = self.relay_actor_config.DeEnergizedState

    def my_channel(self) -> DataChannel:
        relay_config = next(
            (
                config
                for config in self._component.gt.ConfigList
                if config.ActorName == self.name
            ),
            None,
        )
        if relay_config is None:
            raise Exception(f"relay {self.name} does not have a state channel!")
        return self.layout.data_channels[relay_config.ChannelName]

    def _process_event_message(
        self, from_name: str, message: FsmEvent
    ) -> Result[bool, BaseException]:
        from_node = self.layout.node(from_name)
        if from_node is None:
            return Ok(False)
        if message.FromHandle != from_node.handle:
            self.send_warning(
                "bad_sender",
                f"{from_node.name} (handle {from_node.handle}) sent a command claiming "
                f"FromHandle {message.FromHandle}. Ignoring!",
            )
            return Ok(False)

        if message.ToHandle != self.node.Handle:
            self.log(f"Handle is {self.node.Handle}; ignoring {message}")
            self._send_to(
                from_node,
                command_reply.nack(
                    self.node.handle, message.FromHandle, message.TriggerId,
                    ScadaCmdRefusalReason.NotMyBoss,
                ),
            )
            return Ok(False)

        if (
            message.EventType != self.my_event_enum.enum_name()
            or message.EventName not in self.my_event_enum.values()
        ):
            self.log(f"Not a {self.my_event_enum.enum_name()} event. Refusing: {message}")
            self._send_to(
                from_node,
                command_reply.nack(
                    self.node.handle, message.FromHandle, message.TriggerId,
                    ScadaCmdRefusalReason.UnknownEvent,
                ),
            )
            return Ok(False)

        self._send_to(
            from_node,
            command_reply.ack(self.node.handle, message.FromHandle, message.TriggerId),
        )
        if isinstance(self._component, I2cRelayComponent):
            return self._process_event_i2c(from_node, message)

        orig_state = self.state
        self.trigger(message.EventName)

        if self.state == orig_state:
            return Ok(True)

        self._actuate_and_report(
            orig_state=orig_state,
            message=message,
        )

        return Ok(True)

    def _process_event_i2c(
        self, boss: ShNode, message: FsmEvent
    ) -> Result[bool, BaseException]:
        """Command-and-confirm: the FSM commits only after the actuation is
        confirmed, so the event spawns an async actuation task rather than
        triggering the machine here. A re-command of the current state
        actuates anyway (idempotent write, fresh confirmation, fresh report)."""
        cfg = self.relay_actor_config
        if message.EventName == cfg.DeEnergizingEvent:
            pin_value = 0
            target_state = cfg.DeEnergizedState
            relay_pin_event = ChangeRelayPin.DeEnergize
        elif message.EventName == cfg.EnergizingEvent:
            pin_value = 1
            target_state = cfg.EnergizedState
            relay_pin_event = ChangeRelayPin.Energize
        else:
            self.log(
                f"Ignoring event {message.EventName}: not the "
                f"{cfg.EventType} energizing/de-energizing pair"
            )
            return Ok(False)
        command = I2cCommand(
            pin_value=pin_value,
            target_state=target_state,
            event_name=message.EventName,
            relay_pin_event=relay_pin_event,
            trigger_id=message.TriggerId,
            boss=boss,
            send_time_ms=message.SendTimeUnixMs,
        )
        self._i2c_command = command
        self.services.add_task(
            asyncio.create_task(
                self._attempt_command(command),
                name=f"{self.name}-actuate-{message.TriggerId}",
            )
        )
        return Ok(True)

    def _actuate_and_report(
        self,
        *,
        orig_state: str,
        message: FsmEvent,
    ) -> None:
        """
        Perform hardware actuation and ensure FSM reporting is completed.
        Exactly one FsmFullReport will be sent per TriggerId.
        """
        from_node = self.layout.node_by_handle(message.FromHandle)
        assert from_node
        if message.EventName == self.de_energizing_event:
            relay_pin_event = ChangeRelayPin.DeEnergize
            old_pin_state = RelayPinState.Energized
            new_pin_state = RelayPinState.DeEnergized
        else:
            relay_pin_event = ChangeRelayPin.Energize
            old_pin_state = RelayPinState.DeEnergized
            new_pin_state = RelayPinState.Energized

        report = FsmAtomicReport(
            MachineHandle=self.node.handle,
            StateEnum=self.my_state_enum.enum_name(),
            ReportType=FsmReportType.Event,
            EventEnum=self.my_event_enum.enum_name(),
            Event=message.EventName,
            FromState=orig_state,
            ToState=self.state,
            UnixTimeMs=message.SendTimeUnixMs,
            TriggerId=message.TriggerId,
        )

        self.reports_by_trigger[message.TriggerId] = [report]
        self.boss_by_trigger[message.TriggerId] = from_node
        

        """Actuate relay and complete FSM reporting"""
        if isinstance(self._component, GpioRelayComponent):
            self.services.add_task(
                asyncio.create_task(
                    self._gpio_actuate_and_report(
                        relay_pin_event,
                        old_pin_state,
                        new_pin_state,
                        message
                    ),
                    name=f"{self.name}-actuate-{message.TriggerId}",
                )
            )
        else:
            raise Exception(f"Unsupported relay component {type(self._component)}")

    async def _gpio_actuate_and_report(
        self,
        relay_pin_event: ChangeRelayPin,
        old_pin_state: RelayPinState,
        new_pin_state: RelayPinState,
        message: FsmEvent,
    ) -> None:
        now_ms = int(time.time() * 1000)
        error = await self.drive.set(relay_pin_event)
        if error is not None:
            # The machine moved when the command arrived and nothing here
            # retries, so the boss is left without its report and the glitch
            # is the only word that the relay did not follow.
            self._send_glitch(
                "relay-actuation-failed",
                f"{message.EventName}: {error}; no report sent, machine "
                f"holds {self.state}",
                LogLevel.Critical,
            )
            return
        self.log(f"{relay_pin_event} set")

        self.reports_by_trigger[message.TriggerId].append(
            FsmAtomicReport(
                MachineHandle=self.node.handle,
                StateEnum="relay.pin",
                ReportType=FsmReportType.Event,
                EventEnum=ChangeRelayPin.enum_name(),
                Event=relay_pin_event,
                FromState=old_pin_state.value,
                ToState=new_pin_state.value,
                UnixTimeMs=now_ms,
                TriggerId=message.TriggerId,
            )
        )
        boss = self.boss_by_trigger.get(message.TriggerId)
        if boss is not None:
            self.send_state(now_ms=now_ms)
            self._send_to(
                command_reply.report_destination(boss, self.primary_scada),
                FsmFullReport(
                    FromName=self.name,
                    TriggerId=message.TriggerId,
                    AtomicList=self.reports_by_trigger[message.TriggerId]
                )
            )

    async def _read_pin_confirmed(
        self, expected_pin: int
    ) -> tuple[int | None, str | None]:
        """A single garbled read must not be believed: a reading that
        disagrees with expectation is confirmed by a second read 0.5 s later
        (the OPS-452 false-positive guard) before anyone acts on it. The
        pair is the pin value (None on a failed read) and the error text."""
        pin, error = await self._read_pin_with_error()
        if pin is None or pin == expected_pin:
            return pin, error
        await asyncio.sleep(0.5)
        return await self._read_pin_with_error()

    async def _read_pin(self) -> int | None:
        """The pin value the relay holds: 1 energized, 0 de-energized,
        None on a failed read."""
        pin, _error = await self._read_pin_with_error()
        return pin

    async def _read_pin_with_error(self) -> tuple[int | None, str | None]:
        """The pin value with the error text kept: (value, None) on a
        good read, (None, error) on a failed one."""
        read = await self.drive.read()
        return pin_of(read.position), read.error

    def _send_glitch(self, summary: str, details: str, level: LogLevel) -> None:
        self._send_to(
            self.ltn,
            Glitch(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                Node=self.name,
                Type=level,
                Summary=summary,
                Details=details,
            ),
        )

    async def _assert_pin(self, pin_value: int) -> str | None:
        """Set the relay and, where the drive reads back, confirm it at
        the pin. Returns an error description on failure, None on success."""
        error = await self.drive.set(pin_action(pin_value))
        if error is not None:
            return f"write failed: {error}"
        if self.drive.reads_back:
            pin, read_error = await self._read_pin_confirmed(pin_value)
            if pin is None:
                forensics = await self.drive.evidence()
                return f"confirming readback failed: {read_error}; {forensics}"
            if pin != pin_value:
                forensics = await self.drive.evidence()
                return (
                    f"commanded pin {pin_value}, pin reads {pin}; {forensics}"
                )
        return None

    def _commit_command(self, command: I2cCommand) -> None:
        """Confirmation succeeded: commit the FSM, report to the boss, and
        clear the enforcement target — unless a newer command superseded
        this one, in which case its attempt owns the outcome."""
        if self._i2c_command is not command:
            return
        self._i2c_command = None
        self._enforce_failing = False
        orig_state = self.state
        now_ms = int(time.time() * 1000)
        if self.state == UNKNOWN_STATE:
            self.machine.set_state(command.target_state)
        else:
            self.trigger(command.event_name)
        # A no-known-prior actuation (commanded-belief boot assert) reports
        # as a self-loop: there is no honest FromState to name.
        from_state = (
            orig_state if orig_state != UNKNOWN_STATE else command.target_state
        )
        old_pin_state = (
            RelayPinState.DeEnergized
            if command.pin_value == 1
            else RelayPinState.Energized
        )
        new_pin_state = (
            RelayPinState.Energized
            if command.pin_value == 1
            else RelayPinState.DeEnergized
        )
        reports = [
            FsmAtomicReport(
                MachineHandle=self.node.handle,
                StateEnum=self.my_state_enum.enum_name(),
                ReportType=FsmReportType.Event,
                EventEnum=self.my_event_enum.enum_name(),
                Event=command.event_name,
                FromState=from_state,
                ToState=self.state,
                UnixTimeMs=command.send_time_ms,
                TriggerId=command.trigger_id,
            ),
            FsmAtomicReport(
                MachineHandle=self.node.handle,
                StateEnum="relay.pin",
                ReportType=FsmReportType.Event,
                EventEnum=ChangeRelayPin.enum_name(),
                Event=command.relay_pin_event,
                FromState=old_pin_state.value,
                ToState=new_pin_state.value,
                UnixTimeMs=now_ms,
                TriggerId=command.trigger_id,
            ),
        ]
        self.send_state(now_ms=now_ms)
        self._send_to(
            command_reply.report_destination(command.boss, self.primary_scada),
            FsmFullReport(
                FromName=self.name,
                TriggerId=command.trigger_id,
                AtomicList=reports,
            ),
        )

    async def _attempt_command(self, command: I2cCommand) -> None:
        """One attempt at the commanded transition. On failure the command
        stays as the enforcement target and the verify loop retries it."""
        try:
            await asyncio.wait_for(
                self._ready.wait(), timeout=self.READY_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            self._send_glitch(
                "i2c-relay-not-ready",
                f"{command.event_name} deferred: boot adoption has not "
                "completed; the verify loop will retry",
                LogLevel.Critical,
            )
            return
        if self._i2c_command is not command:
            return
        error = await self._assert_pin(command.pin_value)
        if error is not None:
            self._enforce_failing = True
            self._send_glitch(
                "i2c-relay-actuation-failed",
                f"{command.event_name}: {error}; holding as enforcement "
                f"target — retrying at {self.RETRY_BACKOFF_S} s, then every "
                "verify pass",
                LogLevel.Critical,
            )
            self.drive.check()
            self.services.add_task(
                asyncio.create_task(
                    self._retry_command(command),
                    name=f"{self.name}-retry-{command.trigger_id}",
                )
            )
            return
        self._commit_command(command)

    async def _retry_command(self, command: I2cCommand) -> None:
        """The short backoff after a failed attempt. Each retry re-asserts
        the target; a success commits it, a failure asks the drive for a check
        again (debounced there). A newer command ends the retries, and the
        verify pass owns the target after the last one."""
        for delay in self.RETRY_BACKOFF_S:
            await asyncio.sleep(delay)
            if self._i2c_command is not command:
                return
            error = await self._assert_pin(command.pin_value)
            if error is None:
                self.log(f"{command.event_name} confirmed on retry")
                self._commit_command(command)
                return
            self.log(f"retry of {command.event_name} still failing: {error}")
            self.drive.check()

    async def _boot_adopt(self) -> None:
        """Readback boards adopt state from the pins at boot — a latched hold
        left by a stopped service is inherited as confirmed state, not
        overwritten. No-readback boards stay Unknown until the
        first command asserts a posture."""
        if not self.drive.reads_back:
            self._ready.set()
            return
        pin: int | None = None
        for _attempt in range(3):
            pin = await self._read_pin()
            if pin is not None:
                break
            await asyncio.sleep(1)
        if pin is None:
            self._send_glitch(
                "i2c-relay-boot-adopt-failed",
                "could not read the pin at boot; state stays unreported "
                "until the first confirmed actuation",
                LogLevel.Critical,
            )
            self._ready.set()
            return
        cfg = self.relay_actor_config
        adopted = cfg.EnergizedState if pin == 1 else cfg.DeEnergizedState
        self.machine.set_state(adopted)
        self._ready.set()
        self.send_state()

    async def _verify_and_report(self) -> None:
        """The 5-minute enforcement: re-assert the target unconditionally
        (the summer hack's enforce / the krida maintain loop — enforcement
        must not depend on the readback being trustworthy), then confirm at
        the pin. The target is the pending command if one is unconfirmed
        (converge-on-intent retry), else the machine's confirmed state. The
        position the device says it was told is read first purely for the
        drift evidence trail."""
        if not self._ready.is_set():
            return
        command = self._i2c_command
        if command is not None:
            error = await self._assert_pin(command.pin_value)
            if error is not None:
                if not self._enforce_failing:
                    self._enforce_failing = True
                    self._send_glitch(
                        "i2c-relay-enforce-failed",
                        f"retry of {command.event_name}: {error}",
                        LogLevel.Critical,
                    )
                else:
                    self.log(
                        f"retry of {command.event_name} still failing: {error}"
                    )
                self.drive.check()
                return
            self.log(f"{command.event_name} confirmed on verify-pass retry")
            self._commit_command(command)
            return
        if self.state == UNKNOWN_STATE:
            return
        cfg = self.relay_actor_config
        expected_pin = 1 if self.state == cfg.EnergizedState else 0
        if self.drive.reads_back:
            drifted = pin_of(await self.drive.told())
            if drifted is not None and drifted != expected_pin:
                self._send_glitch(
                    "i2c-relay-drift",
                    f"output register held {drifted} where state "
                    f"{self.state} expects {expected_pin}; re-asserting",
                    LogLevel.Warning,
                )
        error = await self._assert_pin(expected_pin)
        if error is not None:
            if not self._enforce_failing:
                self._enforce_failing = True
                self._send_glitch(
                    "i2c-relay-enforce-failed",
                    f"re-assert of pin {expected_pin} for state "
                    f"{self.state}: {error}",
                    LogLevel.Critical,
                )
            else:
                self.log(f"enforce still failing: {error}")
            self.drive.check()
            return
        self._enforce_failing = False
        self.send_state()

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        if isinstance(message.Payload, FsmEvent):
            return self._process_event_message(
                from_name=message.Header.Src, message=message.Payload
            )
        heard = self.drive.hears(message.Payload)
        if heard == Heard.Repaired:
            # Re-assert immediately rather than at the next 5-minute
            # verify pass.
            self.services.add_task(
                asyncio.create_task(
                    self._verify_and_report(),
                    name=f"{self.name}-reset-reassert",
                )
            )
        if heard != Heard.NotMine:
            return Ok(True)

        return Err(
            ValueError(
                f"Error. Relay {self.name} receieved unexpected message: {message.Header}"
            )
        )

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.STATE_REPORT_S * 2.1)]

    def start(self) -> None:
        if isinstance(self._component, I2cRelayComponent):
            self.services.add_task(
                asyncio.create_task(
                    self._boot_adopt(), name=f"{self.name}-boot-adopt"
                )
            )
        self.services.add_task(
            asyncio.create_task(self.main(), name="relay state reporter")
        )

    async def main(self) -> None:
        await asyncio.sleep(2)
        self.send_state()

        while not self._stop_requested:
            hiccup = 1.2
            sleep_s = max(
                hiccup, self.STATE_REPORT_S - (time.time() % self.STATE_REPORT_S) - 2
            )
            await asyncio.sleep(sleep_s)
            if sleep_s != hiccup:
                if isinstance(self._component, I2cRelayComponent):
                    await self._verify_and_report()
                else:
                    self.send_state()
                self._send(PatInternalWatchdogMessage(src=self.name))

    def stop(self) -> None:
        """
        IOLoop will take care of shutting down webserver interaction.
        Here we stop periodic reporting task.
        """
        self._stop_requested = True

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""
        ...

    def send_state(self, now_ms: Optional[int] = None) -> None:
        if self.state == UNKNOWN_STATE:
            # Internal-only: no wire value exists for Unknown, and an
            # out-of-vocab value would decode as the enum default.
            return
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        # self.log(f"[{self.my_channel().Name}] {self.state}")
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=self.my_state_enum.enum_name(),
                State=self.state,
                UnixMs=now_ms,
            ),
        )
        # The same confirmed state as a reading on the RelayState channel:
        # 1 energized, 0 de-energized.
        self._send_to(
            self.primary_scada,
            SingleReading(
                ChannelName=self.my_channel().Name,
                Value=1 if self.state == self.relay_actor_config.EnergizedState else 0,
                ScadaReadTimeUnixMs=now_ms,
            ),
        )

    def _initialize_fsm_from_config(self) -> None:
        """The FSM vocabulary comes from the layout's relay.control.config
        (EventType/StateType), not node-name matching — one relay actor,
        layout-bound semantics. Initial state is the internal Unknown until
        boot adoption or the first confirmed actuation."""
        cfg = self.relay_actor_config
        event_enum = EVENT_ENUM_BY_NAME.get(cfg.EventType)
        if event_enum is None:
            raise ValueError(
                f"{self.name}: no event enum registered for EventType "
                f"{cfg.EventType}"
            )
        state_enum = STATE_ENUM_BY_NAME.get(cfg.StateType)
        if state_enum is None:
            raise ValueError(
                f"{self.name}: no state enum registered for StateType "
                f"{cfg.StateType}"
            )
        self.my_event_enum = event_enum
        self.my_state_enum = state_enum
        self.de_energized_state = cfg.DeEnergizedState
        self.transitions = [
            {
                "trigger": cfg.DeEnergizingEvent,
                "source": cfg.EnergizedState,
                "dest": cfg.DeEnergizedState,
            },
            {
                "trigger": cfg.DeEnergizingEvent,
                "source": cfg.DeEnergizedState,
                "dest": cfg.DeEnergizedState,
            },
            {
                "trigger": cfg.EnergizingEvent,
                "source": cfg.DeEnergizedState,
                "dest": cfg.EnergizedState,
            },
            {
                "trigger": cfg.EnergizingEvent,
                "source": cfg.EnergizedState,
                "dest": cfg.EnergizedState,
            },
        ]
        self.machine = Machine(
            model=self,
            states=[*state_enum.values(), UNKNOWN_STATE],
            transitions=self.transitions,
            initial=UNKNOWN_STATE,
            send_event=True,
        )

    def initialize_fsm(self):
        if isinstance(self._component, I2cRelayComponent):
            self._initialize_fsm_from_config()
            return
        self.my_state_enum = RelayClosedOrOpen
        self.my_event_enum = ChangeRelayState
        self.de_energized_state = "RelayClosed"
        circuits = self.layout.hydronic.ZoneCallCircuits
        stat_failsafe_names = [c.FailsafeRelayNode for c in circuits]
        stat_ops_names = [c.OpsRelayNode for c in circuits]
        vdc_relay_name = self.layout.vdc_relay.name
    
        if self.name in {
            vdc_relay_name,
            House0NodeNames.tstat_common_relay,
            HSNN.hp_scada_ops_relay,
            self.layout.store_pump_relay.name,
            House0NodeNames.primary_pump_scada_ops,
            House0NodeNames.hp_loop_on_off,
        } | set(stat_ops_names):
        
            if self.name in {
                vdc_relay_name,
                House0NodeNames.tstat_common_relay,
                HSNN.hp_scada_ops_relay,
                House0NodeNames.hp_loop_on_off
            }:
                if self.de_energizing_event != ChangeRelayState.CloseRelay:
                    raise Exception(
                        f"Expect CloseRelay as de-energizing event for {self.name}; got {self.de_energizing_event}"
                    )
            else:
                if self.de_energizing_event != ChangeRelayState.OpenRelay:
                    raise Exception(
                        f"Expect OpenRelay as de-energizing event for {self.name}; got {self.de_energizing_event}"
                    )

        elif self.name == House0NodeNames.store_charge_discharge_relay:
            self.my_state_enum = StoreFlowRelay
            self.my_event_enum = ChangeStoreFlowRelay
            if self.de_energizing_event != ChangeStoreFlowRelay.DischargeStore:
                raise Exception(
                    f"Expect DischargeStore as de-energizing event for {self.name}; got {self.de_energizing_event}"
                )

        elif self.name == House0NodeNames.hp_failsafe_relay:
            self.my_state_enum = HeatPumpControl
            self.my_event_enum = ChangeHeatPumpControl
            if self.de_energizing_event != ChangeHeatPumpControl.SwitchToTankAquastat:
                raise Exception(
                    f"Expect SwitchToTankAquastat as de-energizing event for {self.name}; got {self.de_energizing_event}"
                )
        elif self.name == House0NodeNames.aquastat_ctrl_relay:
            self.my_state_enum = AquastatControl
            self.my_event_enum = ChangeAquastatControl
            if self.de_energizing_event != ChangeAquastatControl.SwitchToBoiler:
                raise Exception(
                    f"Expect SwitchToBoiler as de-energizing event for {self.name}; got {self.de_energizing_event}"
                )

        elif self.name == House0NodeNames.primary_pump_failsafe:
            self.my_state_enum = PrimaryPumpControl
            self.my_event_enum = ChangePrimaryPumpControl
            if self.de_energizing_event != ChangePrimaryPumpControl.SwitchToHeatPump:
                raise Exception(
                    f"Expect SwitchToHeatPump as de-energizing event for {self.name}; got {self.de_energizing_event}"
                )
        elif self.name == House0NodeNames.hp_loop_keep_send:
            self.my_state_enum = HpLoopKeepSend
            self.my_event_enum = ChangeKeepSend
            if self.de_energizing_event != ChangeKeepSend.ChangeToKeepLess:
                raise Exception(f"Expect ChangeToSendMore as de-energizing event for {self.name}!")
        elif self.name in stat_failsafe_names:
            self.my_state_enum = ZoneCallSource
            self.my_event_enum = ChangeZoneCallSource
            if self.de_energizing_event != ChangeZoneCallSource.SwitchToWallThermostat:
                raise Exception(
                    f"Expect SwitchToWallThermostat as de-energizing event for {self.name}; got {self.de_energizing_event}"
                )
        
        if self.relay_actor_config is None:
            raise Exception(f"relay control config cannot be none for {self.name}")
        self.transitions = [
                {
                    "trigger": self.relay_actor_config.DeEnergizingEvent,
                    "source": self.relay_actor_config.EnergizedState,
                    "dest": self.relay_actor_config.DeEnergizedState,
                },
                {
                    "trigger": self.relay_actor_config.DeEnergizingEvent,
                    "source": self.relay_actor_config.DeEnergizedState,
                    "dest": self.relay_actor_config.DeEnergizedState,
                },
                {
                    "trigger": self.relay_actor_config.EnergizingEvent,
                    "source":self.relay_actor_config.DeEnergizedState,
                    "dest": self.relay_actor_config.EnergizedState,
                },
                {
                    "trigger": self.relay_actor_config.EnergizingEvent,
                    "source": self.relay_actor_config.EnergizedState,
                    "dest":  self.relay_actor_config.EnergizedState,
                },
            ]
        try:
            self.machine = Machine(
                model=self,
                states=self.my_state_enum.values(),
                transitions=self.transitions,
                initial=self.relay_actor_config.DeEnergizedState,
                send_event=True,
            )

        except AttributeError as e:
            self.log(f"PROBLEM with {self.node}!: {e}")
