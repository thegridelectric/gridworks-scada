"""NolanBufferOnlyTou: the Nolan family's heating machine, charging the
buffer on the time-of-use schedule and leaving the store alone.

The state names the one plant decision the machine makes, the heat-pump
call: closed off-peak while the buffer band wants charge, open on-peak or
when the band is full. The band is a latch on two channels: buffer depth3
at or above the full threshold sets it, depth1 below the charge threshold
clears it, and it holds in between. Either channel stale beyond five
minutes blinds the band; the top machine then runs ScadaBlind, where the
scada-blind node drives the call on the schedule alone and the heat
pump's own limits stop it when the buffer is hot.

The postures are not states. Every zone is on its thermostat with the
scada relay open; the store circuit is closed; the secondary pump and iso
valve follow the hp-sensor machine's state, to which this machine
subscribes: off while the heat pump is detected off, on while it is
detected on and while the state is unknown. The pump is commanded the
moment a state arrives. The loop derives the postures each check and
commands a change; the relay layer's assert-then-verify holds the pins
between commands.
"""

import asyncio
import time
from datetime import datetime, timedelta
from enum import auto
from typing import Optional, Sequence

from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from result import Ok, Result
from transitions import Machine

from actors.hp_boss.sensing import HP_TRAITS, HpTraits
from actors.hydronic.nolan import NolanHydronic
from actors.in_process_messages import MachineStateSubscribe
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import (
    ChangeRelayState,
    ChangeValveState,
    ChangeZoneCallSource,
    LocalControlTopEvent,
    LocalControlTopState,
    NolanLcBufferOnlyState,
    SpruceHackHpState,
)
from gwsproto.enums.gw_str_enum import SemaEnum
from gwsproto.named_types import (
    ActuatorsReady,
    GoDormant,
    NolanFamilyParams,
    SingleMachineState,
    WakeUp,
)
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.channel_names import (
    HydronicSpaceheatChannelNames as HCN,
)
from gwsproto.names.hydronic_spaceheat.node_names import (
    HydronicSpaceheatNodeNames as HSNN,
)
from gwsproto.names.nolan.node_names import NolanNodeNames
from scada_app_interface import ScadaAppInterface


class NolanLcBufferOnlyEvent(SemaEnum):
    """The events that move the Nolan heating machine's call between the
    gw1.nolan.lc.buffer.only.state values; each transition reports its
    event as the SingleMachineState Cause. Local to this machine and not a
    published sema word."""

    Boot = auto()
    CallOn = auto()
    CallOff = auto()
    CallGoDormant = auto()
    CallWakeUp = auto()

    @classmethod
    def default(cls) -> "NolanLcBufferOnlyEvent":
        return cls.CallWakeUp

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.nolan.lc.buffer.only.event"

    @classmethod
    def enum_version(cls) -> str:
        return "000"


class NolanBufferOnlyTou(NolanHydronic):
    MAIN_LOOP_SLEEP_SECONDS = 300
    TOU_CHECK_S = 60.0
    BLIND_S = 300.0

    REQUIRED_NODES = (
        NolanNodeNames.iso_valve_relay,
        NolanNodeNames.secondary_pump_relay,
        NolanNodeNames.charge_valve_relay,
        HSNN.store_pump_relay,
        HSNN.hp_scada_ops_relay,
    )

    top_states = LocalControlTopState.values()
    top_transitions = [
        {
            "trigger": LocalControlTopEvent.MonitorOnly,
            "source": LocalControlTopState.Normal,
            "dest": LocalControlTopState.Monitor,
        },
        {
            "trigger": LocalControlTopEvent.MonitorAndControl,
            "source": LocalControlTopState.Monitor,
            "dest": LocalControlTopState.Normal,
        },
        {
            "trigger": LocalControlTopEvent.MissingData,
            "source": LocalControlTopState.Normal,
            "dest": LocalControlTopState.ScadaBlind,
        },
        {
            "trigger": LocalControlTopEvent.DataAvailable,
            "source": LocalControlTopState.ScadaBlind,
            "dest": LocalControlTopState.Normal,
        },
        {
            "trigger": LocalControlTopEvent.TopGoDormant,
            "source": LocalControlTopState.Normal,
            "dest": LocalControlTopState.Dormant,
        },
        {
            "trigger": LocalControlTopEvent.TopGoDormant,
            "source": LocalControlTopState.Monitor,
            "dest": LocalControlTopState.Dormant,
        },
        {
            "trigger": LocalControlTopEvent.TopGoDormant,
            "source": LocalControlTopState.ScadaBlind,
            "dest": LocalControlTopState.Dormant,
        },
        {
            "trigger": LocalControlTopEvent.TopWakeUp,
            "source": LocalControlTopState.Dormant,
            "dest": LocalControlTopState.Normal,
        },
    ]

    call_states = NolanLcBufferOnlyState.values()
    call_transitions = [
        {
            "trigger": NolanLcBufferOnlyEvent.Boot,
            "source": NolanLcBufferOnlyState.Initializing,
            "dest": NolanLcBufferOnlyState.HpCallOff,
        },
        {
            "trigger": NolanLcBufferOnlyEvent.CallOn,
            "source": NolanLcBufferOnlyState.HpCallOff,
            "dest": NolanLcBufferOnlyState.HpCallOn,
        },
        {
            "trigger": NolanLcBufferOnlyEvent.CallOff,
            "source": NolanLcBufferOnlyState.HpCallOn,
            "dest": NolanLcBufferOnlyState.HpCallOff,
        },
        {
            "trigger": NolanLcBufferOnlyEvent.CallGoDormant,
            "source": [NolanLcBufferOnlyState.Initializing, NolanLcBufferOnlyState.HpCallOn, NolanLcBufferOnlyState.HpCallOff],
            "dest": NolanLcBufferOnlyState.Dormant,
        },
        {
            "trigger": NolanLcBufferOnlyEvent.CallWakeUp,
            "source": NolanLcBufferOnlyState.Dormant,
            "dest": NolanLcBufferOnlyState.Initializing,
        },
    ]

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self._stop_requested: bool = False
        self.actuators_ready = False
        self.check_required_nodes(self.REQUIRED_NODES)
        family = self.ops.FamilyParams
        if not isinstance(family, NolanFamilyParams):
            raise ValueError(
                f"NolanBufferOnlyTou needs gw.nolan.family.params, got {family.TypeName}"
            )
        self.family: NolanFamilyParams = family
        hp_odu = self.required_node(HSNN.hp_odu).component
        if hp_odu is None:
            raise ValueError(f"{HSNN.hp_odu} has no component; cannot read its device type")
        device_type = hp_odu.gt.DeviceType
        self.traits: HpTraits = HP_TRAITS[device_type]
        self.zone_relays: list[tuple[ShNode, ShNode]] = [
            (
                self.required_node(c.FailsafeRelayNode),
                self.required_node(c.OpsRelayNode),
            )
            for c in sorted(
                self.layout.hydronic.ZoneCallCircuits or [],
                key=lambda c: c.CircuitPosition,
            )
        ]
        self.buffer_full: bool = False
        # The heat pump as hp-sensor last reported it; Unknown until a
        # state arrives.
        self.hp_state: SpruceHackHpState = SpruceHackHpState.Unknown
        # The commanded secondary-pump state; None until the first decision.
        self.pump_on: Optional[bool] = None
        # Whether the hp-boss was last commanded to a closed call.
        self.call_closed: Optional[bool] = None
        self.top_machine = Machine(
            model=self,
            states=NolanBufferOnlyTou.top_states,
            transitions=NolanBufferOnlyTou.top_transitions,
            initial=LocalControlTopState.Normal,
            send_event=True,
            model_attribute="top_state",
        )
        self.top_state: LocalControlTopState = LocalControlTopState.Normal
        self.call_machine = Machine(
            model=self,
            states=NolanBufferOnlyTou.call_states,
            transitions=NolanBufferOnlyTou.call_transitions,
            initial=NolanLcBufferOnlyState.Initializing,
            send_event=True,
            model_attribute="call_state",
        )
        self.call_state: NolanLcBufferOnlyState = NolanLcBufferOnlyState.Initializing
        self.set_command_tree(boss_node=self.normal_node)
        self.log(
            f"Starting NolanBufferOnlyTou in Normal (band "
            f"{self.family.BufferChargeF}-{self.family.BufferFullF} F, "
            f"call opens {self.traits.call_open_lead_s} s before on-peak, "
            f"for {device_type})"
        )

    @property
    def normal_node(self) -> ShNode:
        return self.required_node(CoreNodeNames.local_control_normal)

    @property
    def boss(self) -> ShNode:
        """The node commanding the plant: scada-blind while the band is
        blind, normal otherwise."""
        if self.top_state == LocalControlTopState.ScadaBlind:
            return self.layout.local_control_scada_blind_node
        return self.normal_node

    # ---- reporting ----

    def trigger_top_event(self, cause: LocalControlTopEvent) -> None:
        orig_state = self.top_state
        getattr(self, cause.value)()
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=LocalControlTopState.enum_name(),
                State=self.top_state,
                UnixMs=int(time.time() * 1000),
                Cause=cause.value,
            ),
        )
        self.log(f"{cause}: {orig_state} -> {self.top_state}")

    def trigger_call_event(self, event: NolanLcBufferOnlyEvent) -> None:
        orig_state = self.call_state
        getattr(self, event.value)()
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.normal_node.handle,
                StateEnum=NolanLcBufferOnlyState.enum_name(),
                State=self.call_state,
                UnixMs=int(time.time() * 1000),
                Cause=event.value,
            ),
        )
        self.log(f"{event.value}: {orig_state} -> {self.call_state}")

    # ---- the band ----

    def buffer_fresh(self) -> bool:
        """Both band channels read within BLIND_S."""
        now_ms = time.time() * 1000
        for name in (HCN.buffer.depth1, HCN.buffer.depth3):
            read_ms = self.data.latest_channel_unix_ms.get(name)
            if read_ms is None or now_ms - read_ms > self.BLIND_S * 1000:
                return False
        return True

    def update_band(self) -> None:
        """Set the latch when depth3 reaches the full threshold, clear it
        when depth1 falls below the charge threshold, hold otherwise. A
        blind band leaves the latch alone."""
        if not self.buffer_fresh():
            return
        top = self.channel_temperature(HCN.buffer.depth1)
        bottom = self.channel_temperature(HCN.buffer.depth3)
        if top is None or bottom is None:
            return
        if bottom.f >= self.family.BufferFullF:
            if not self.buffer_full:
                self.log(f"buffer full: depth3 {bottom.f:.1f} F; call held open")
            self.buffer_full = True
        elif top.f < self.family.BufferChargeF:
            if self.buffer_full:
                self.log(f"buffer wants charge: depth1 {top.f:.1f} F")
            self.buffer_full = False

    def offpeak(self, now: datetime) -> bool:
        """Outside every on-peak window, and not within the heat pump's
        call-open lead of one opening; the lead pads the start of each
        window only, so the end is the tariff's own."""
        lead = timedelta(seconds=self.traits.call_open_lead_s)
        return not self.in_onpeak_window(now) and not self.in_onpeak_window(now + lead)

    # ---- the postures ----

    def pump_wanted(self) -> bool:
        """Off while hp-sensor says the heat pump is off; on while it says
        on and while it does not know."""
        return self.hp_state != SpruceHackHpState.HpDetectedOff

    def enforce_pump(self) -> None:
        wanted = self.pump_wanted()
        if wanted == self.pump_on:
            return
        self.send_state_command(
            self.layout.secondary_pump_relay,
            ChangeRelayState.CloseRelay.value if wanted else ChangeRelayState.OpenRelay.value,
            from_node=self.boss,
        )
        self.send_state_command(
            self.layout.iso_valve,
            ChangeValveState.OpenValve.value if wanted else ChangeValveState.CloseValve.value,
            from_node=self.boss,
        )
        self.pump_on = wanted

    def command_call(self, closed: bool) -> None:
        if closed:
            self.turn_on_hp(from_node=self.boss)
        else:
            self.turn_off_hp(from_node=self.boss)
        self.call_closed = closed

    def boot(self) -> None:
        """The boot posture, commanded once the actuators are ready: zones
        on their thermostats, the store circuit closed, the call open, the
        pump per the hp-sensor state. Initializing -> HpCallOff."""
        for failsafe, ops_relay in self.zone_relays:
            self.send_state_command(
                failsafe,
                ChangeZoneCallSource.SwitchToWallThermostat.value,
                from_node=self.boss,
            )
            self.send_state_command(
                ops_relay, ChangeRelayState.OpenRelay.value, from_node=self.boss
            )
        self.send_state_command(
            self.required_node(NolanNodeNames.charge_valve_relay),
            ChangeValveState.CloseValve.value,
            from_node=self.boss,
        )
        self.send_state_command(
            self.required_node(HSNN.store_pump_relay),
            ChangeRelayState.OpenRelay.value,
            from_node=self.boss,
        )
        self.command_call(False)
        self.pump_on = None
        self.enforce_pump()
        self.trigger_call_event(NolanLcBufferOnlyEvent.Boot)

    # ---- the check, every TOU_CHECK_S ----

    def check(self, now: datetime) -> None:
        if not self.actuators_ready or self.top_state in (
            LocalControlTopState.Dormant,
            LocalControlTopState.Monitor,
        ):
            return
        fresh = self.buffer_fresh()
        if self.top_state == LocalControlTopState.Normal and not fresh:
            self.trigger_top_event(LocalControlTopEvent.MissingData)
            self.set_command_tree(boss_node=self.boss)
            self.trigger_call_event(NolanLcBufferOnlyEvent.CallGoDormant)
        elif self.top_state == LocalControlTopState.ScadaBlind and fresh:
            self.trigger_top_event(LocalControlTopEvent.DataAvailable)
            self.set_command_tree(boss_node=self.boss)
            self.trigger_call_event(NolanLcBufferOnlyEvent.CallWakeUp)
            self.boot()
        if self.top_state == LocalControlTopState.Normal:
            self.update_band()
            wanted = self.offpeak(now) and not self.buffer_full
            if wanted and self.call_state == NolanLcBufferOnlyState.HpCallOff:
                self.command_call(True)
                self.trigger_call_event(NolanLcBufferOnlyEvent.CallOn)
            elif not wanted and self.call_state == NolanLcBufferOnlyState.HpCallOn:
                self.command_call(False)
                self.trigger_call_event(NolanLcBufferOnlyEvent.CallOff)
        else:
            wanted = self.offpeak(now)
            if wanted != self.call_closed:
                self.command_call(wanted)
        self.enforce_pump()

    # ---- messages ----

    def on_actuators_ready(self) -> None:
        if not self.actuators_ready:
            self.actuators_ready = True
            self.boot()

    def go_dormant(self) -> None:
        if len(self.my_actuators()) > 0:
            raise Exception("LocalControl sent GoDormant with live actuators under it!")
        if self.top_state != LocalControlTopState.Dormant:
            self.trigger_top_event(LocalControlTopEvent.TopGoDormant)
        if self.call_state != NolanLcBufferOnlyState.Dormant:
            self.trigger_call_event(NolanLcBufferOnlyEvent.CallGoDormant)

    def wake_up(self) -> None:
        """A released tree is re-booted, never resumed."""
        if self.top_state != LocalControlTopState.Dormant:
            return
        self.trigger_top_event(LocalControlTopEvent.TopWakeUp)
        self.set_command_tree(boss_node=self.normal_node)
        self.trigger_call_event(NolanLcBufferOnlyEvent.CallWakeUp)
        self.boot()

    def on_hp_sensor_state(self, state: SpruceHackHpState) -> None:
        """The pump follows the moment a state arrives, when this machine
        holds the tree."""
        self.hp_state = state
        if not self.actuators_ready or self.top_state in (
            LocalControlTopState.Dormant,
            LocalControlTopState.Monitor,
        ):
            return
        self.enforce_pump()

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        from_node = self.layout.node(message.Header.Src, None)
        if from_node is None:
            self.log("Not processing message from message.Header.Src - no Node!")
            return Ok(True)
        payload = message.Payload
        match payload:
            case ActuatorsReady():
                self.on_actuators_ready()
            case SingleMachineState():
                if (
                    from_node.name == HSNN.hp_sensor
                    and payload.StateEnum == SpruceHackHpState.enum_name()
                ):
                    self.on_hp_sensor_state(SpruceHackHpState(payload.State))
            case GoDormant():
                self.go_dormant()
            case WakeUp():
                self.wake_up()
        return Ok(True)

    # ---- lifecycle ----

    def start(self) -> None:
        self._send_to(self.primary_scada, MachineStateSubscribe(NodeName=HSNN.hp_sensor))
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=LocalControlTopState.enum_name(),
                State=self.top_state,
                UnixMs=int(time.time() * 1000),
            ),
        )
        self.services.add_task(
            asyncio.create_task(self.main(), name="NolanBufferOnlyTou keepalive")
        )
        self.services.add_task(
            asyncio.create_task(self.tou_loop(), name="NolanBufferOnlyTou tou")
        )

    def stop(self) -> None:
        self._stop_requested = True

    async def join(self):
        ...

    def init(self) -> None:
        ...

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.MAIN_LOOP_SLEEP_SECONDS * 2.1)]

    async def main(self):
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)

    async def tou_loop(self) -> None:
        while not self._stop_requested:
            await asyncio.sleep(self.TOU_CHECK_S)
            try:
                self.check(datetime.now(self.timezone))
            except Exception as e:  # noqa: BLE001
                self.log(f"NolanBufferOnlyTou check failed: {e}")
