"""Implements Relay Actors"""
import asyncio
import time
import uuid
from typing import Dict, List, NamedTuple, Sequence, Optional

from gwsproto.enums import SemaEnum
from gwproto.message import Message
from gwsproto.data_classes.data_channel import DataChannel
from gwproactor import  MonitoredName
from gwproactor.message import PatInternalWatchdogMessage

from drivers import tca9555
from gwsproto.data_classes.components import (
    I2cMultichannelDtRelayComponent,
    I2cRelayComponent,
    GpioRelayComponent,
)
from gwsproto.data_classes.house_0_names import H0N, ZoneNodes
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import (
    ActorClass,
    AquastatControl,
    ChangeAquastatControl,
    ChangeHeatPumpControl,
    ChangePrimaryPumpControl,
    ChangeRelayPin,
    ChangeRelayState,
    ChangeStoreFlowRelay,
    ChangeHeatcallSource,
    ChangeValveState,
    ChangeZoneCallSource,
    FsmReportType,
    HeatPumpControl,
    PrimaryPumpControl,
    RelayClosedOrOpen,
    RelayPinState,
    RelayWiringConfig,
    StoreFlowRelay,
    HeatcallSource,
    ValveOpenOrClosed,
    ZoneCallSource,

)

from gwsproto.named_types import (
    FsmAtomicReport,
    FsmFullReport,
    I2cBitAddress,
    I2cReadBit,
    I2cReadReg,
    I2cRegAddress,
    I2cResult,
    I2cWriteBit,
)
from gwsproto.property_format import NonNegativeInt, UTCMilliseconds, UUID4Str
from result import Err, Ok, Result
from transitions import Machine
from actors.sh_node_actor import ShNodeActor
from scada_app_interface import ScadaAppInterface
from gwsproto.enums import LogLevel, ChangeKeepSend, HpLoopKeepSend
from gwsproto.named_types import FsmEvent, Glitch, SingleMachineState

# Internal FSM state before the first pin adoption / confirmation. Never
# published: the state vocabularies carry no Unknown value, and an
# out-of-vocab wire value coerces to the enum default at decode.
UNKNOWN_STATE = "Unknown"

# The control vocabularies an i2c relay's config may declare. The config's
# EventType/StateType (left.right.dot enum names) select the FSM vocabulary —
# layout-driven, no node-name matching.
EVENT_ENUM_BY_NAME: dict[str, type[SemaEnum]] = {
    e.enum_name(): e for e in (ChangeRelayState, ChangeZoneCallSource, ChangeValveState)
}
STATE_ENUM_BY_NAME: dict[str, type[SemaEnum]] = {
    s.enum_name(): s for s in (RelayClosedOrOpen, ZoneCallSource, ValveOpenOrClosed)
}


class I2cActuation(NamedTuple):
    """Physical actuation facts for one board-resident i2c relay, resolved
    once at init from the board record: where the bit lives (bus node, chip
    address, output/input/config registers, bit index) and whether the board
    supports pin readback (confirmed vs commanded-belief semantics). Field
    types mirror i2c.bit.address."""

    bus_node: ShNode
    i2c_address: NonNegativeInt
    output_register: NonNegativeInt
    input_register: NonNegativeInt
    config_register: NonNegativeInt
    bit_index: NonNegativeInt
    supports_readback: bool


class I2cCommand(NamedTuple):
    """A commanded transition not yet confirmed at the pin. Held as the
    relay's enforcement target until confirmation succeeds — the verify loop
    retries it (converge-on-intent, the summer hack's enforce behavior), so a
    transient bus failure heals without the boss re-commanding. A newer
    command supersedes it. Field types mirror the wire: pin_value is
    i2c.write.bit's 0/1 (NonNegativeInt + BitValueRange, so not PositiveInt);
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
    BUS_OP_TIMEOUT_S = 1.0
    READY_TIMEOUT_S = 10.0
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
            self._component,
            (I2cMultichannelDtRelayComponent, I2cRelayComponent, GpioRelayComponent)
        ):
            raise ValueError(f"Component for {self.name} has type "
                             f"{type(self._component)}. Expected "
                             "I2cMultichannelDtRelayComponent, "
                             "I2cRelayComponent or GpioRelayComponent")

        self.relay_actor_config = next(
            (x for x in self._component.gt.ConfigList if x.ActorName == self.node.name),
            None,
        )

        if self.relay_actor_config is None:
            raise Exception(
                f"Relay {self.node.name} not in component {self._component}'s RelayActorConfigList:\n"
                f"{self._component.gt.ConfigList}"
            )

        self.de_energizing_event = self.relay_actor_config.DeEnergizingEvent
        self.reports_by_trigger = {}
        self.boss_by_trigger = {}
        self.my_event_enum: type[SemaEnum] = ChangeRelayState
        self.my_state_enum: type[SemaEnum] = RelayClosedOrOpen

        self._i2c: I2cActuation | None = None
        self._i2c_command: I2cCommand | None = None
        self._enforce_failing = False
        self._pending_results: dict[str, "asyncio.Future[I2cResult]"] = {}
        self._ready = asyncio.Event()
        if isinstance(self._component, I2cRelayComponent):
            self._i2c = self._resolve_i2c_actuation()

        self.relay_multiplexer: ShNode | None = None
        if isinstance(self._component, I2cMultichannelDtRelayComponent):
            self.relay_multiplexer = self.layout.node(H0N.relay_multiplexer)

        self.initialize_fsm()
        self._stop_requested = False
        if not isinstance(self._component, I2cRelayComponent):
            self.state = self.relay_actor_config.DeEnergizedState

        self._gpio_pin: int | None = None
        if isinstance(self._component, GpioRelayComponent):
            self._gpio_pin = self._resolve_gpio_pin()

        if not self.settings.is_simulated:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            self.GPIO.setmode(GPIO.BCM)
            if self._gpio_pin is not None:
                self.GPIO.setup(self._gpio_pin, GPIO.OUT)
        else:
            self.GPIO = None

    def _resolve_gpio_pin(self) -> int:
        """GpioName resolved against the NativeGpioOutputs of the layout's
        board device-type records — the board record carries the physical
        BCM pin."""
        gpio_name = self._component.gt.GpioName
        for record in self.layout.device_types.values():
            for pin in getattr(record, "NativeGpioOutputs", []):
                if pin.Name == gpio_name:
                    return pin.BcmPin
        raise ValueError(
            f"{self.name}: no board device-type record in the layout carries "
            f"a native GPIO output named {gpio_name}"
        )

    def _resolve_i2c_actuation(self) -> I2cActuation:
        """RelayName resolved against THIS component's board record — the
        record's I2cRelays map holds the physical address (expander, output
        register, bit); the layout never restates it."""
        assert isinstance(self._component, I2cRelayComponent)
        record = self._component.board_component.device_type
        relay_name = self._component.gt.RelayName
        capability = next(
            (r for r in record.I2cRelays if r.RelayName == relay_name), None
        )
        if capability is None:
            raise ValueError(
                f"{self.name}: board record {record.DeviceType} has no "
                f"I2cRelays entry named {relay_name}"
            )
        expander = next(
            (
                e
                for e in record.Expanders
                if e.ExpanderIdx == capability.ExpanderIdx
            ),
            None,
        )
        if expander is None:
            raise ValueError(
                f"{self.name}: board record {record.DeviceType} has no "
                f"expander with ExpanderIdx {capability.ExpanderIdx}"
            )
        bus_nodes = [
            n
            for n in self.layout.nodes.values()
            if n.ActorClass == ActorClass.I2cBus
        ]
        if len(bus_nodes) != 1:
            raise ValueError(
                f"{self.name}: expected exactly one I2cBus node in the "
                f"layout; found {len(bus_nodes)}"
            )
        return I2cActuation(
            bus_node=bus_nodes[0],
            i2c_address=expander.I2cAddress,
            output_register=capability.RegisterIndex,
            input_register=tca9555.input_register(capability.RegisterIndex),
            config_register=tca9555.config_register(capability.RegisterIndex),
            bit_index=capability.BitIndex,
            supports_readback=record.SupportsPinReadback,
        )


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
            self.log(
                f"from_node {from_node.name} has handle {from_node.handle}, not {message.FromHandle}!"
            )
            return Ok(False)

        if message.ToHandle != self.node.Handle:
            # TODO: turn this into a report?
            self._send_to(self.ltn,
                          Glitch(
                              FromGNodeAlias=self.layout.scada_g_node_alias,
                              Node=self.name,
                              Type=LogLevel.Warning,
                              Summary="bad_boss",
                              Details=f"{message.FromHandle} tried to command {self.node.Handle}. Ignoring!"
                          ))
            self.log(f"Handle is {self.node.Handle}; ignoring {message}")
            return Ok(False)

        if message.EventType != self.my_event_enum.enum_name():
            print(f"Not a {self.my_event_enum} event type. Ignoring: {message}")

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
            self._gpio_actuate_and_report(
                relay_pin_event,
                old_pin_state,
                new_pin_state,
                message
            )
        elif isinstance(self._component, I2cMultichannelDtRelayComponent):
            self._krida_actuate(relay_pin_event, message)
        else:
            raise Exception(f"Unsupported relay component {type(self._component)}")

    def _krida_actuate(
        self, relay_pin_event: ChangeRelayPin, message: FsmEvent
    ) -> None:
        """Actuate via the legacy krida multiplexer: commanded belief only.
        The multiplexer moves the pin and reports state on its own channels;
        the relay-side confirmation round-trip does not exist on this
        component type, so the boss receives no FsmFullReport."""
        if self.relay_multiplexer is None:
            self._send_glitch(
                "krida-multiplexer-missing",
                f"{message.EventName} dropped: the layout has no "
                f"{H0N.relay_multiplexer} node",
                LogLevel.Critical,
            )
            return
        self._send_to(
            self.relay_multiplexer,
            FsmEvent(
                FromHandle=self.node.handle,
                ToHandle=self.relay_multiplexer.handle,
                EventType=ChangeRelayPin.enum_name(),
                EventName=relay_pin_event,
                TriggerId=message.TriggerId,
                SendTimeUnixMs=int(time.time() * 1000),
            ),
        )
        
    def _gpio_actuate_and_report(
        self,
        relay_pin_event: ChangeRelayPin,
        old_pin_state: RelayPinState,
        new_pin_state: RelayPinState,
        message: FsmEvent,
    ) -> None:
        now_ms = int(time.time() * 1000)
        if self.settings.is_simulated:
            self.log("Simulated relay actuation; skipping GPIO")
            return

        pin = self._gpio_pin
        if relay_pin_event == ChangeRelayPin.Energize:
            self.GPIO.output(pin, self.GPIO.HIGH)
            self.log(f"Energizing: Setting pin {pin} to High")
        else:
            self.GPIO.output(pin, self.GPIO.LOW)
            self.log(f"De-energizing: Setting pin {pin} to Low")

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
                boss,
                FsmFullReport(
                    FromName=self.name,
                    TriggerId=message.TriggerId,
                    AtomicList=self.reports_by_trigger[message.TriggerId]
                )
            )

    async def _bus_op(
        self, payload: I2cWriteBit | I2cReadBit | I2cReadReg
    ) -> I2cResult | None:
        """Send one op to the bus actor and await its I2cResult (None on
        timeout)."""
        assert self._i2c is not None
        future: "asyncio.Future[I2cResult]" = (
            asyncio.get_running_loop().create_future()
        )
        self._pending_results[payload.TriggerId] = future
        self._send_to(self._i2c.bus_node, payload)
        try:
            return await asyncio.wait_for(future, timeout=self.BUS_OP_TIMEOUT_S)
        except asyncio.TimeoutError:
            self._pending_results.pop(payload.TriggerId, None)
            return None

    async def _read_pin_confirmed(self, expected_pin: int) -> int | None:
        """A single garbled i2c read must not be believed: a reading that
        disagrees with expectation is confirmed by a second read 0.5 s later
        (the OPS-452 false-positive guard) before anyone acts on it."""
        pin = await self._read_pin()
        if pin is None or pin == expected_pin:
            return pin
        await asyncio.sleep(0.5)
        return await self._read_pin()

    async def _read_pin(self) -> int | None:
        """The actual level at the relay's pin, via the expander's input-port
        register. None on bus failure."""
        a = self._i2c
        assert a is not None
        result = await self._bus_op(
            I2cReadBit(
                Bus=a.bus_node.name,
                Address=I2cBitAddress(
                    I2cAddress=a.i2c_address,
                    RegisterIndex=a.input_register,
                    BitIndex=a.bit_index,
                ),
                TriggerId=str(uuid.uuid4()),
            )
        )
        if result is None or not result.Success:
            return None
        return result.Value

    async def _write_pin(self, pin_value: int) -> str | None:
        """Drive the relay's output-register bit. Returns an error string on
        failure, None on success."""
        a = self._i2c
        assert a is not None
        result = await self._bus_op(
            I2cWriteBit(
                Bus=a.bus_node.name,
                Address=I2cBitAddress(
                    I2cAddress=a.i2c_address,
                    RegisterIndex=a.output_register,
                    BitIndex=a.bit_index,
                ),
                Value=pin_value,
                TriggerId=str(uuid.uuid4()),
            )
        )
        if result is None:
            return "bus op timeout"
        if not result.Success:
            return result.Error or "bus op failed"
        return None

    async def _register_forensics(self) -> str:
        """Snapshot the expander's output and config registers for the port —
        the diagnostic pair that separates a stuck pin (output right, input
        wrong) from the reset signature (config back in input mode)."""
        a = self._i2c
        assert a is not None
        readings = []
        for label, register in (
            ("output", a.output_register),
            ("config", a.config_register),
        ):
            result = await self._bus_op(
                I2cReadReg(
                    Bus=a.bus_node.name,
                    Address=I2cRegAddress(
                        I2cAddress=a.i2c_address, RegisterIndex=register
                    ),
                    NumBytes=1,
                    TriggerId=str(uuid.uuid4()),
                )
            )
            if result is None or not result.Success or result.Value is None:
                readings.append(f"{label}[{register}]=unreadable")
            else:
                readings.append(f"{label}[{register}]=0x{result.Value:02x}")
        return " ".join(readings)

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

    async def _read_output_bit(self) -> int | None:
        """The commanded flip-flop bit (output register) — read before the
        periodic re-assert purely as drift evidence (the 07-16 tell was
        output bits reading 1 forty minutes after being set 0)."""
        a = self._i2c
        assert a is not None
        result = await self._bus_op(
            I2cReadBit(
                Bus=a.bus_node.name,
                Address=I2cBitAddress(
                    I2cAddress=a.i2c_address,
                    RegisterIndex=a.output_register,
                    BitIndex=a.bit_index,
                ),
                TriggerId=str(uuid.uuid4()),
            )
        )
        if result is None or not result.Success:
            return None
        return result.Value

    async def _assert_pin(self, pin_value: int) -> str | None:
        """Drive the bit and, on a readback board, confirm it at the pin.
        Returns an error description on failure, None on success."""
        a = self._i2c
        assert a is not None
        error = await self._write_pin(pin_value)
        if error is not None:
            return f"write failed: {error}"
        if a.supports_readback:
            pin = await self._read_pin_confirmed(pin_value)
            if pin is None:
                return "confirming readback failed"
            if pin != pin_value:
                forensics = await self._register_forensics()
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
            command.boss,
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
                "target — retrying every verify pass",
                LogLevel.Critical,
            )
            return
        self._commit_command(command)

    async def _boot_adopt(self) -> None:
        """Readback boards adopt state from the pins at boot — a latched hold
        left by a stopped service is inherited as confirmed state, not
        overwritten. No-readback boards (and sim) stay Unknown until the
        first command asserts a posture."""
        a = self._i2c
        assert a is not None
        if not a.supports_readback:
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
        output register is read first purely for the drift evidence trail."""
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
                return
            self.log(f"{command.event_name} confirmed on verify-pass retry")
            self._commit_command(command)
            return
        if self.state == UNKNOWN_STATE:
            return
        a = self._i2c
        assert a is not None
        cfg = self.relay_actor_config
        expected_pin = 1 if self.state == cfg.EnergizedState else 0
        if a.supports_readback:
            drifted = await self._read_output_bit()
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
            return
        self._enforce_failing = False
        self.send_state()

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        if isinstance(message.Payload, FsmEvent):
            return self._process_event_message(
                from_name=message.Header.Src, message=message.Payload
            )
        if isinstance(message.Payload, I2cResult):
            future = self._pending_results.pop(message.Payload.TriggerId, None)
            if future is not None and not future.done():
                future.set_result(message.Payload)
            # a late reply after timeout is dropped; the timeout already
            # glitched
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
        zone_names = self.layout.zone_list
        stat_failsafe_names = []
        stat_ops_names = []
        # TODO: move the below into House0 Hardware Layout validation
        for i, zone in enumerate(zone_names):
            zone_nodes = ZoneNodes(zone=zone, idx=i)
            stat_failsafe_names.append(zone_nodes.failsafe_relay)
            stat_ops_names.append(zone_nodes.ops_relay)
        vdc_relay_name = self.layout.vdc_relay.name
    
        if self.name in {
            vdc_relay_name,
            H0N.tstat_common_relay,
            H0N.hp_scada_ops_relay,
            H0N.thermistor_common_relay,
            H0N.store_pump_failsafe,
            H0N.primary_pump_scada_ops,
            H0N.hp_loop_on_off,
        } | set(stat_ops_names):
        
            if self.name in {
                vdc_relay_name,
                H0N.tstat_common_relay,
                H0N.hp_scada_ops_relay,
                H0N.thermistor_common_relay,
                H0N.hp_loop_on_off
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

        elif self.name == H0N.store_charge_discharge_relay:
            self.my_state_enum = StoreFlowRelay
            self.my_event_enum = ChangeStoreFlowRelay
            if self.de_energizing_event != ChangeStoreFlowRelay.DischargeStore:
                raise Exception(
                    f"Expect DischargeStore as de-energizing event for {self.name}; got {self.de_energizing_event}"
                )

        elif self.name == H0N.hp_failsafe_relay:
            self.my_state_enum = HeatPumpControl
            self.my_event_enum = ChangeHeatPumpControl
            if self.de_energizing_event != ChangeHeatPumpControl.SwitchToTankAquastat:
                raise Exception(
                    f"Expect SwitchToTankAquastat as de-energizing event for {self.name}; got {self.de_energizing_event}"
                )
        elif self.name == H0N.aquastat_ctrl_relay:
            self.my_state_enum = AquastatControl
            self.my_event_enum = ChangeAquastatControl
            if self.de_energizing_event != ChangeAquastatControl.SwitchToBoiler:
                raise Exception(
                    f"Expect SwitchToBoiler as de-energizing event for {self.name}; got {self.de_energizing_event}"
                )

        elif self.name == H0N.primary_pump_failsafe:
            self.my_state_enum = PrimaryPumpControl
            self.my_event_enum = ChangePrimaryPumpControl
            if self.de_energizing_event != ChangePrimaryPumpControl.SwitchToHeatPump:
                raise Exception(
                    f"Expect SwitchToHeatPump as de-energizing event for {self.name}; got {self.de_energizing_event}"
                )
        elif self.name == H0N.hp_loop_keep_send:
            self.my_state_enum = HpLoopKeepSend
            self.my_event_enum = ChangeKeepSend
            if self.de_energizing_event != ChangeKeepSend.ChangeToKeepLess:
                raise Exception(f"Expect ChangeToSendMore as de-energizing event for {self.name}!")
        elif self.name in stat_failsafe_names:
            self.my_state_enum = HeatcallSource
            self.my_event_enum = ChangeHeatcallSource
            if self.de_energizing_event != ChangeHeatcallSource.SwitchToWallThermostat:
                raise Exception(
                    f"Expect SwitchToWallThermostat as de-energizing event for {self.name}; got {self.de_energizing_event}"
                )
        
        if self.relay_actor_config is None:
            raise Exception(f"RelayActorConfig cannot be none for {self.name}")
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
