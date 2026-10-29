from typing import Literal, Self
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import PrimaryFlowSource
from sema_snapshot.sema.enums import PrimaryPumpOwner
from sema_snapshot.sema.enums import RefrigerantCycle
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.types.boiler_backup import BoilerBackup
from sema_snapshot.sema.types.circulator import Circulator
from sema_snapshot.sema.types.element_backup import ElementBackup
from sema_snapshot.sema.types.hvac_zone import HvacZone
from sema_snapshot.sema.types.water_store import WaterStore
from sema_snapshot.sema.types.zone_call_circuit import ZoneCallCircuit


class Hydronic(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.hydronic/000"""

    zones: list[HvacZone]
    zone_call_circuits: list[ZoneCallCircuit]
    circulators: list[Circulator]
    water_store: WaterStore | None = None
    backup: BoilerBackup | ElementBackup | None = None
    primary_flow_source: PrimaryFlowSource
    primary_pump_owner: PrimaryPumpOwner
    refrigerant_cycle: RefrigerantCycle
    hp_command_node_name: SpaceheatName | None = None
    type_name: Literal["gw.hydronic"] = "gw.hydronic"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Cardinality
        The number of Zones SHALL be between 1 and 6 inclusive.
        """
        if not 1 <= len(self.zones) <= 6:
            raise ValueError(
                "Axiom 1 (Cardinality) failed: number of Zones "
                f"({len(self.zones)}) must be between 1 and 6 inclusive."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: CircuitResolution
        a. Every circuit's ServesZone SHALL equal the Name of a zone in
        Zones. b. The circuit at 1-based place i in ZoneCallCircuits SHALL
        have CircuitPosition i.
        c. No two zones SHALL share a Name.
        """
        circuits = self.zone_call_circuits or []
        zone_names = {z.name for z in self.zones}
        for c in circuits:
            if c.serves_zone not in zone_names:
                raise ValueError(
                    "Axiom 2 (CircuitResolution) failed: ServesZone "
                    f"{c.serves_zone!r} does not name a zone in Zones."
                )
        positions = [c.circuit_position for c in circuits]
        if positions != list(range(1, len(circuits) + 1)):
            raise ValueError(
                "Axiom 2 (CircuitResolution) failed: CircuitPosition values "
                f"{positions} are not each circuit's 1-based place in ZoneCallCircuits."
            )
        names = [z.name for z in self.zones]
        if len(names) != len(set(names)):
            raise ValueError(
                f"Axiom 2 (CircuitResolution) failed: zone Names {names} are not distinct."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: PrimaryCircuit
        a. Every zone's PrimaryCircuitPosition SHALL equal the
        CircuitPosition of a circuit whose ServesZone equals the zone's
        Name. b. That circuit SHALL carry SetpointChannelName.
        """
        circuits = {c.circuit_position: c for c in (self.zone_call_circuits or [])}
        for zone in self.zones:
            primary = circuits.get(zone.primary_circuit_position)
            if primary is None or primary.serves_zone != zone.name:
                raise ValueError(
                    f"Axiom 3 (PrimaryCircuit) failed: zone {zone.name!r} names "
                    f"PrimaryCircuitPosition {zone.primary_circuit_position}, which is "
                    "not the position of a circuit serving it."
                )
            if not primary.setpoint_channel_name:
                raise ValueError(
                    f"Axiom 3 (PrimaryCircuit) failed: zone {zone.name!r}'s primary "
                    f"circuit {primary.name!r} carries no SetpointChannelName."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: CircuitDistinctness
        a. No two circuits SHALL share a Name. b. No two circuits SHALL
        share a WhitewireChannelName. c. No two circuits SHALL share a
        SetpointChannelName. d. No two circuits SHALL share a
        TempChannelName. e. No two circuits SHALL share a FailsafeRelayNode.
        f. No two circuits SHALL share an OpsRelayNode.
        """
        circuits = self.zone_call_circuits or []
        for field, values in (
            ("Name", [c.name for c in circuits]),
            ("WhitewireChannelName", [c.whitewire_channel_name for c in circuits]),
            (
                "SetpointChannelName",
                [c.setpoint_channel_name for c in circuits if c.setpoint_channel_name],
            ),
            (
                "TempChannelName",
                [c.temp_channel_name for c in circuits if c.temp_channel_name],
            ),
            ("FailsafeRelayNode", [c.failsafe_relay_node for c in circuits]),
            ("OpsRelayNode", [c.ops_relay_node for c in circuits]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(
                    f"Axiom 4 (CircuitDistinctness) failed: {field} values {values} "
                    "are not distinct."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> Self:
        """
        Axiom 5: CirculatorDistinctness
        No two circulators SHALL share a PumpNodeName.
        """
        names = [c.pump_node_name for c in (self.circulators or [])]
        if len(names) != len(set(names)):
            raise ValueError(
                f"Axiom 5 (CirculatorDistinctness) failed: PumpNodeName values {names} "
                "are not distinct."
            )
        return self
