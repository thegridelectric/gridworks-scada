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
valve follow measured heat-pump power, on above the on-threshold, off on
the first read below the off-threshold, on while the power is unknown.
The loop derives the postures each check and commands a change; the
relay layer's assert-then-verify holds the pins between commands.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, Sequence

from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from result import Ok, Result
from transitions import Machine

from actors.hp_boss.sensing import HP_TRAITS, HpTraits
from actors.hydronic.nolan import NolanHydronic
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import (
    ChangeRelayState,
    ChangeValveState,
    ChangeZoneCallSource,
    LocalControlTopEvent,
    LocalControlTopState,
    NolanLcBufferOnlyState,
    TurnHpOnOff,
)
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
        {"trigger": "MonitorOnly", "source": "Normal", "dest": "Monitor"},
        {"trigger": "MonitorAndControl", "source": "Monitor", "dest": "Normal"},
        {"trigger": "MissingData", "source": "Normal", "dest": "ScadaBlind"},
        {"trigger": "DataAvailable", "source": "ScadaBlind", "dest": "Normal"},
        {"trigger": "TopGoDormant", "source": "Normal", "dest": "Dormant"},
        {"trigger": "TopGoDormant", "source": "Monitor", "dest": "Dormant"},
        {"trigger": "TopGoDormant", "source": "ScadaBlind", "dest": "Dormant"},
        {"trigger": "TopWakeUp", "source": "Dormant", "dest": "Normal"},
    ]

    call_states = NolanLcBufferOnlyState.values()
    call_transitions = [
        {"trigger": "Boot", "source": "Initializing", "dest": "HpCallOff"},
        {"trigger": "CallOn", "source": "HpCallOff", "dest": "HpCallOn"},
        {"trigger": "CallOff", "source": "HpCallOn", "dest": "HpCallOff"},
        {
            "trigger": "CallGoDormant",
            "source": ["Initializing", "HpCallOn", "HpCallOff"],
            "dest": "Dormant",
        },
        {"trigger": "CallWakeUp", "source": "Dormant", "dest": "Initializing"},
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
        traits = HP_TRAITS.get(device_type)
        if traits is None:
            raise ValueError(
                f"No heat-pump traits for hp-odu device type "
                f"{device_type}; NolanBufferOnlyTou cannot run this layout"
            )
        self.traits: HpTraits = traits
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
            f"pump {self.traits.on_above_w}/{self.traits.off_below_w} W, "
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

    def trigger_call_event(self, event: str) -> None:
        orig_state = self.call_state
        getattr(self, event)()
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.normal_node.handle,
                StateEnum=NolanLcBufferOnlyState.enum_name(),
                State=self.call_state,
                UnixMs=int(time.time() * 1000),
                Cause=event,
            ),
        )
        self.log(f"{event}: {orig_state} -> {self.call_state}")

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
        """On above the on-threshold, off below the off-threshold, held
        between; on while the heat-pump power is unknown."""
        if not self.channel_is_live(HCN.hp_odu_pwr):
            return True
        watts = self.data.latest_channel_values.get(HCN.hp_odu_pwr)
        if watts is None:
            return True
        if watts > self.traits.on_above_w:
            return True
        if watts < self.traits.off_below_w:
            return False
        return True if self.pump_on is None else self.pump_on

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
        self.send_state_command(
            self.layout.hp_boss,
            TurnHpOnOff.TurnOn.value if closed else TurnHpOnOff.TurnOff.value,
            from_node=self.boss,
        )
        self.call_closed = closed

    def boot(self) -> None:
        """The boot posture, commanded once the actuators are ready: zones
        on their thermostats, the store circuit closed, the call open, the
        pump per the power rule. Initializing -> HpCallOff."""
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
        self.trigger_call_event("Boot")

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
            self.trigger_call_event("CallGoDormant")
        elif self.top_state == LocalControlTopState.ScadaBlind and fresh:
            self.trigger_top_event(LocalControlTopEvent.DataAvailable)
            self.set_command_tree(boss_node=self.boss)
            self.trigger_call_event("CallWakeUp")
            self.boot()
        if self.top_state == LocalControlTopState.Normal:
            self.update_band()
            wanted = self.offpeak(now) and not self.buffer_full
            if wanted and self.call_state == NolanLcBufferOnlyState.HpCallOff:
                self.command_call(True)
                self.trigger_call_event("CallOn")
            elif not wanted and self.call_state == NolanLcBufferOnlyState.HpCallOn:
                self.command_call(False)
                self.trigger_call_event("CallOff")
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
            self.trigger_call_event("CallGoDormant")

    def wake_up(self) -> None:
        """A released tree is re-booted, never resumed."""
        if self.top_state != LocalControlTopState.Dormant:
            return
        self.trigger_top_event(LocalControlTopEvent.TopWakeUp)
        self.set_command_tree(boss_node=self.normal_node)
        self.trigger_call_event("CallWakeUp")
        self.boot()

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        from_node = self.layout.node(message.Header.Src, None)
        if from_node is None:
            self.log("Not processing message from message.Header.Src - no Node!")
            return Ok(True)
        match message.Payload:
            case ActuatorsReady():
                self.on_actuators_ready()
            case GoDormant():
                self.go_dormant()
            case WakeUp():
                self.wake_up()
        return Ok(True)

    # ---- lifecycle ----

    def start(self) -> None:
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
