from typing import Any, Protocol
from gwsproto.data_classes.sh_node import ShNode
from actors.scada_data import ScadaData
from gwsproto.data_classes.house_0_layout import House0Layout

class ProceduralHost(Protocol):
    """
    Structural protocol for actors that host procedural, non-transactive
    interrupts (e.g. pump doctor, watchdog recovery).
    """

    @property
    def command_node(self) -> ShNode:
        """
        The ShNode that sits at the top of the command tree.

        This may change mid-flight as the state machine changes
        """
        ...


    # belongs to ShNodActors

    @property
    def node(self) -> ShNode:
        """Audit / identity node (used for glitches, attribution)."""
        ...


    @property
    def ltn(self) -> ShNode:
        """ Must return `ltn` ShNode"""
        ...

    @property
    def primary_scada(self) -> ShNode:
        """ Must return primary scada ShNode"""
        ...

    @property
    def dist_010v(self) -> ShNode:
        """Must return dist 010v Node"""
        ...

    @property
    def store_010v(self) -> ShNode:
        ...

    @property
    def primary_010v(self) -> ShNode:
        ...

    def _send_to(self, dst: ShNode, payload: Any, src: ShNode | None = None) -> None: ...

    @property 
    def layout(self) -> House0Layout: ...

    async def await_with_watchdog(
            self, 
            total_seconds: float, 
            pat_every: float = 20
            ) -> None: 
        """
        Await for up to total_seconds while maintaining watchdog health.
        Must emit periodic internal PAT messages.
        """
        ...

    def set_010_defaults(self, boss_node: ShNode | None = None) -> None: ...

    def stat_ops_open_relay(self, zone: str, boss_node: ShNode| None = None) -> None: ...

    def heatcall_ctrl_to_scada(self, zone: str, boss_node: ShNode | None = None) -> None:
        ...

    def stat_ops_close_relay(self, zone: str, boss_node: ShNode | None = None) -> None:
        ...

    def turn_off_store_pump(self, boss_node: ShNode | None = None) -> None: 
        ...

    def turn_on_store_pump(self, boss_node: ShNode | None = None) -> None: 
        ...

    def primary_pump_failsafe_to_hp(self, boss_node: ShNode | None = None) -> None:
        ...

    def primary_pump_failsafe_to_scada(self, boss_node: ShNode | None = None) -> None:
        ...

    def turn_off_primary_pump(self, boss_node: ShNode | None = None) -> None:
        ...

    def turn_on_primary_pump(self, boss_node: ShNode | None = None) -> None:
        ...

    def heatcall_ctrl_to_stat(self, zone: str, boss_node: ShNode | None = None) -> None: 
        """
        Return control of the zone heatcall to the wall thermostat.

        Implementations must:
        - Route the command using command_node, using self.node if no command_node provided
        - Perform authority checks appropriate to the current command tree
        - Be safe to call during procedural interrupts
        """
        ...

    @property
    def data(self) -> ScadaData: ...

    def log(self, note: str) -> None: ...
