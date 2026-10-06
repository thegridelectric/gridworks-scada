"""The cold-house judgment and what follows from it, for every family:
whether a critical zone is cold, judged through its primary circuit;
whether the stores are empty; when a leaf ally declines an offer for
cold; and the cold-watch actor, which keeps the setpoint recorded for a
circuit whose setpoint is learned, raises the critical-zone-cold,
still-cold-in-backup and zone-freezing glitches, and breaks a dispatch
contract when the house is cold with the stores empty."""

import asyncio
import time
from typing import NamedTuple, Optional, Sequence

from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto.message import Message
from gwsproto.conversions.temperature import Temperature
from gwsproto.enums import LocalControlTopState, SeasonalStorageMode, ZoneSetpointSource
from gwsproto.named_types import AllyGivesUp, SingleMachineState, SingleReading
from gwsproto.named_types.hvac_zone import HvacZone
from gwsproto.named_types.zone_call_circuit import ZoneCallCircuit
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.property_format import SpaceheatName
from result import Ok, Result

from actors.glitch_limit import REPEAT_GLITCH_S, GlitchLimit
from actors.hydronic.shared import HydronicNode
from actors.in_process_messages import BreakServiceContract, MachineStateSubscribe
from actors.scada_data import save_recorded_setpoints
from scada_app_interface import ScadaAppInterface

COLD_DELTA_F = 2.0  # a critical zone this far under its setpoint is cold
FREEZE_F = 40.0  # any circuit reading under this is freezing
COLD_LATCH_S = 5 * 60  # how long the house is cold before the latch fires
STILL_COLD_IN_BACKUP_S = 60 * 60  # how long cold in backup before saying so

# Glitch summaries, one per condition
CRITICAL_ZONE_COLD = "critical-zone-cold"
STILL_COLD_IN_BACKUP = "still-cold-in-backup"
ZONE_FREEZING = "zone-freezing"


class ColdZone(NamedTuple):
    """A critical zone judged cold. Held in process for the log and the
    glitch text; never serialized."""

    zone: SpaceheatName
    """The zone's Name."""
    temperature: Temperature
    """The reading on the zone's primary circuit's temperature channel."""
    setpoint: Temperature
    """The setpoint the zone was judged against."""

    def line(self) -> str:
        return f"{self.zone} at {self.temperature.f:.1f} F, setpoint {self.setpoint.f:.1f} F"


class FreezingCircuit(NamedTuple):
    """A circuit whose temperature channel reads under FREEZE_F. Held in
    process for the glitch text; never serialized."""

    circuit: SpaceheatName
    """The circuit's Name."""
    zone: SpaceheatName
    """The Name of the zone the circuit serves."""
    temperature: Temperature

    def line(self) -> str:
        return f"{self.circuit} (zone {self.zone}) at {self.temperature.f:.1f} F"


class ColdSpell:
    """How long the house has been cold without a warm check between."""

    def __init__(self) -> None:
        self.since_s: Optional[float] = None

    def held(self, cold: bool, now_s: float) -> bool:
        """Notes one check. True once the house has been cold at every check
        for COLD_LATCH_S."""
        if not cold:
            self.since_s = None
            return False
        if self.since_s is None:
            self.since_s = now_s
        return now_s - self.since_s >= COLD_LATCH_S

    def reset(self) -> None:
        self.since_s = None


class ColdJudgmentNode(HydronicNode):
    """HydronicNode + the cold-house judgment."""

    def refresh_setpoints_at_onpeak_start(self) -> None:
        """Take the current reading of each circuit's setpoint channel,
        keyed by the channel's name, as the setpoint the circuit had when
        on-peak began. A circuit whose setpoint a thermostat reports is
        judged against the lower of this and the current setpoint, so a
        thermostat raised during on-peak does not read as a cold house.
        Refreshed off-peak; held through on-peak."""
        self.setpoints_at_onpeak_start = {}
        for circuit in self.layout.hydronic.ZoneCallCircuits:
            if circuit.SetpointChannelName is None:
                continue
            setpoint = self.channel_temperature(circuit.SetpointChannelName)
            if setpoint is not None:
                self.setpoints_at_onpeak_start[circuit.SetpointChannelName] = setpoint

    def critical_primary_circuits(self) -> list[tuple[HvacZone, ZoneCallCircuit]]:
        """Each critical zone with its primary circuit."""
        circuits = {c.CircuitPosition: c for c in self.layout.hydronic.ZoneCallCircuits}
        return [
            (zone, circuits[zone.PrimaryCircuitPosition])
            for zone in self.layout.hydronic.Zones
            if zone.Critical
        ]

    def recorded_setpoint(self, setpoint_channel_name: SpaceheatName) -> Optional[Temperature]:
        recorded = self.data.recorded_setpoints.get(setpoint_channel_name)
        if recorded is None:
            return None
        return self.layout.channel_registry.temperature(setpoint_channel_name, recorded.Value)

    def thermostat_setpoint(self, setpoint_channel_name: SpaceheatName) -> Optional[Temperature]:
        """The lower of the setpoint at the start of on-peak and the
        current one: a thermostat raised during on-peak does not make the
        house cold, and neither does one lowered."""
        at_onpeak_start = self.setpoints_at_onpeak_start.get(setpoint_channel_name)
        current = self.channel_temperature(setpoint_channel_name)
        if at_onpeak_start is not None and current is not None:
            return min(at_onpeak_start, current)
        return at_onpeak_start if at_onpeak_start is not None else current

    def circuit_is_calling(self, circuit: ZoneCallCircuit) -> bool:
        value = self.data.latest_channel_values.get(self.layout.heat_call_channel(circuit))
        return value is not None and value >= 1

    def cold_critical_zones(self) -> list[ColdZone]:
        """Each critical zone judged cold, with its temperature and the
        setpoint it was judged against. A zone is judged through its
        primary circuit: that circuit's temperature channel, setpoint
        channel, heat call and SetpointSource.

        A circuit whose thermostat reports its setpoint is cold
        COLD_DELTA_F or more under the thermostat setpoint. A circuit whose
        setpoint is learned is cold when it is calling for heat and
        COLD_DELTA_F or more under its recorded setpoint: the call is the
        thermostat saying the zone is under its setpoint, the record says
        by how much."""
        if not self.is_onpeak():  # TODO: bleed into the first half hour of offpeak
            self.refresh_setpoints_at_onpeak_start()
        cold: list[ColdZone] = []
        for zone, circuit in self.critical_primary_circuits():
            if circuit.SetpointChannelName is None or circuit.TempChannelName is None:
                raise ValueError(
                    f"zone {zone.Name}: primary circuit {circuit.Name} carries no "
                    "setpoint and temperature channel"
                )
            temperature = self.channel_temperature(circuit.TempChannelName)
            if temperature is None:
                self.log(f"Could not find latest temperature for {zone.Name}!")
                continue
            if circuit.SetpointSource == ZoneSetpointSource.Learned:
                setpoint = self.recorded_setpoint(circuit.SetpointChannelName)
                if setpoint is None:
                    self.log(f"No recorded setpoint for {zone.Name}!")
                    continue
                if not self.circuit_is_calling(circuit):
                    continue
            else:
                setpoint = self.thermostat_setpoint(circuit.SetpointChannelName)
                if setpoint is None:
                    self.log(f"Could not find setpoint for {zone.Name}!")
                    continue
            if temperature.f <= setpoint.f - COLD_DELTA_F:
                cold.append(ColdZone(zone.Name, temperature, setpoint))
        return cold

    def is_system_cold(self) -> bool:
        """True if at least one critical zone is cold."""
        cold = self.cold_critical_zones()
        if cold:
            self.log(f"Cold: {'; '.join(zone.line() for zone in cold)}")
        else:
            self.log("No critical zone is cold")
        return bool(cold)

    def stores_empty(self) -> bool:
        """The buffer is empty and, when the seasonal storage mode is
        AllTanks, the store is too."""
        if not self.is_buffer_empty():
            return False
        if self.ops.FamilyParams.SeasonalStorageMode == SeasonalStorageMode.AllTanks:
            return self.is_storage_empty()
        return True

    def declines_offer_for_cold(self) -> bool:
        """At a dispatch offer: a critical zone cold now, with the stores
        empty, declines the offer and the ally gives up. No contract was
        broken, so nothing is latched."""
        if not (self.is_system_cold() and self.stores_empty()):
            return False
        self.log("Cannot wake up - system is cold and the stores are empty")
        self._send_to(
            self.primary_scada,
            AllyGivesUp(Reason="System is cold, not entering DispatchContracts"),
        )
        return True


class ColdWatch(ColdJudgmentNode):
    """The actor at the cold-watch node. On its own loop, in every top
    state of the local control, it looks at the house: it keeps the
    recorded setpoints, raises the critical-zone-cold,
    still-cold-in-backup and zone-freezing glitches, and breaks a dispatch
    contract the house cannot keep. It learns whether the
    house is in backup from the local control's top state."""

    WATCH_S = 60

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self._stop_requested = False
        self.in_backup = False
        self.cold_spell = ColdSpell()
        self.cold_reported = False
        self.break_sent = False
        self.backup_since_s: Optional[float] = None
        self.still_cold_reported = False
        self.freeze_glitches = GlitchLimit(REPEAT_GLITCH_S)

    def start(self) -> None:
        self._send_to(
            self.primary_scada, MachineStateSubscribe(NodeName=CoreNodeNames.local_control)
        )
        self.services.add_task(asyncio.create_task(self.main(), name="ColdWatch"))

    def stop(self) -> None:
        self._stop_requested = True

    async def join(self) -> None:
        ...

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.WATCH_S * 2.1)]

    async def main(self) -> None:
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            try:
                self.cold_watch(time.time())
            except Exception as e:  # noqa: BLE001
                self.log(f"Cold watch failed: {e}")
            await asyncio.sleep(self.WATCH_S)

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        payload = message.Payload
        match payload:
            case SingleMachineState():
                if (
                    payload.MachineHandle.split(".")[-1] == CoreNodeNames.local_control
                    and payload.StateEnum == LocalControlTopState.enum_name()
                ):
                    self.in_backup = (
                        payload.State == LocalControlTopState.InBackup
                    )
            case _:
                self.log(f"{self.name} received unexpected message: {message.Header}")
        return Ok(True)

    def record_learned_setpoints(self) -> None:
        """Keep the last reading each critical zone's learned setpoint
        channel carried, and write the record when one changes. The channel
        goes quiet when the generator withdraws its setpoint and is empty
        after a restart; the record is what a cold zone is judged against
        through both."""
        changed = False
        for _, circuit in self.critical_primary_circuits():
            name = circuit.SetpointChannelName
            if name is None or circuit.SetpointSource != ZoneSetpointSource.Learned:
                continue
            value = self.data.latest_channel_values.get(name)
            read_ms = self.data.latest_channel_unix_ms.get(name)
            if value is None or read_ms is None:
                continue
            recorded = self.data.recorded_setpoints.get(name)
            if recorded is not None and recorded.Value == value:
                continue
            self.data.recorded_setpoints[name] = SingleReading(
                ChannelName=name, Value=value, ScadaReadTimeUnixMs=read_ms
            )
            changed = True
        if changed:
            save_recorded_setpoints(
                self.settings, self.layout.scada_g_node_alias, self.data.recorded_setpoints
            )

    def freezing_circuits(self) -> list[FreezingCircuit]:
        """Each circuit, of a critical zone or not, whose temperature
        channel reads under FREEZE_F."""
        freezing: list[FreezingCircuit] = []
        for circuit in self.layout.hydronic.ZoneCallCircuits:
            if circuit.TempChannelName is None:
                continue
            temperature = self.channel_temperature(circuit.TempChannelName)
            if temperature is not None and temperature.f < FREEZE_F:
                freezing.append(FreezingCircuit(circuit.Name, circuit.ServesZone, temperature))
        return freezing

    def cold_watch(self, now_s: float) -> None:
        """One look at the house.

        A critical zone cold for COLD_LATCH_S raises the critical-zone-cold
        glitch, once per cold spell, unless the house is in standby, where
        it may be unheated on purpose. Cold that long with the stores empty
        asks the scada to break any dispatch contract, once per cold spell.
        A house still cold after STILL_COLD_IN_BACKUP_S in backup raises
        its own glitch, once per stay. A circuit reading under FREEZE_F
        raises the zone-freezing glitch."""
        self.record_learned_setpoints()

        for freezing in self.freezing_circuits():
            if self.freeze_glitches.due(freezing.circuit):
                self.alert(ZONE_FREEZING, f"{freezing.line()}, under {FREEZE_F:.0f} F")

        cold = self.cold_critical_zones()
        if not cold:
            self.cold_reported = False
            self.break_sent = False
        if self.cold_spell.held(bool(cold), now_s):
            cause = (
                f"{'; '.join(zone.line() for zone in cold)}. "
                f"Cold for {COLD_LATCH_S // 60} minutes"
            )
            if not self.cold_reported and not self.ops.Standby:
                self.cold_reported = True
                self.alert(CRITICAL_ZONE_COLD, f"{cause}.")
            if not self.break_sent and self.stores_empty():
                self.break_sent = True
                self._send_to(
                    self.primary_scada,
                    BreakServiceContract(Cause=f"{cause} with the stores empty"),
                )

        if not self.in_backup:
            self.backup_since_s = None
            self.still_cold_reported = False
            return
        if self.backup_since_s is None:
            self.backup_since_s = now_s
        if (
            cold
            and not self.still_cold_reported
            and now_s - self.backup_since_s > STILL_COLD_IN_BACKUP_S
        ):
            self.still_cold_reported = True
            self.alert(
                STILL_COLD_IN_BACKUP,
                f"{'; '.join(zone.line() for zone in cold)}. In backup for more than "
                f"{STILL_COLD_IN_BACKUP_S // 60} minutes.",
            )
