import asyncio
import time
import typing
from abc import ABC
from datetime import datetime
from typing import Any, Optional
import pytz


from gwproactor import QOS
from gwproactor.message import PatInternalWatchdogMessage
from gwproactor import Actor
from gwproto import Message

from actors.config import ScadaSettings
from actors.scada_data import ScadaData
from gwsproto.conversions.temperature import Temperature
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.house0.node_names import House0NodeNames
from gwsproto.names.hydronic_spaceheat.node_names import (
    HydronicSpaceheatNodeNames as HSNN,
)

from gwsproto.data_classes.sh_node import ShNode

from gwsproto.enums import (
    DayOfWeek,
    LogLevel,
    RelayClosedOrOpen,
    StoreFlowRelay
)


from gwsproto.named_types import Glitch, HeatingForecast, SingleMachineState
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
from gwsproto.property_format import SpaceheatName

from sema_to_dc import OperationalParams
from scada_app_interface import ScadaAppInterface


class ShNodeActor(Actor, ABC):
    GALLONS_PER_TANK = 120
    NUM_LAYERS_PER_TANK = 3
    GALLON_PER_LITER = 3.78541
    LITERS_PER_LAYER = GALLONS_PER_TANK/NUM_LAYERS_PER_TANK * GALLON_PER_LITER
    WATER_SPECIFIC_HEAT_KJ_PER_KG_C = 4.187
    WATER_SPECIFIC_HEAT_KWH_PER_KG_C = WATER_SPECIFIC_HEAT_KJ_PER_KG_C / 3600
    PUMP_FLOW_GPM_THRESHOLD = 0.1

    def __init__(self, name: str, services: ScadaAppInterface):
        if not isinstance(services, ScadaAppInterface):
            raise ValueError(
                "ERROR. ShNodeActor requires services to be a ScadaAppInterface. "
                f"Received type {type(services)}."
            )
        super().__init__(name, services)
        self.timezone = pytz.timezone(self.ops.Tariff.TimezoneStr)
        # set temperature_channel_names
        self.tank_temp_channel_names = list(HCN.buffer.effective)
        for tank_idx in sorted(self.layout.store_tanks):
            tank = self.layout.store_tanks[tank_idx]
            self.tank_temp_channel_names.extend([tank.depth1, tank.depth2, tank.depth3])

        self.pipe_temp_channel_names = [
            HCN.hp_ewt, HCN.hp_lwt,
             HCN.dist_swt, HCN.dist_rwt, 
            HCN.buffer_cold_pipe, HCN.buffer_hot_pipe, 
            HCN.store_cold_pipe, HCN.store_hot_pipe,
        ]

        self.temperature_channel_names =  self.tank_temp_channel_names + self.pipe_temp_channel_names

        self.setpoints_at_onpeak_start: dict[SpaceheatName, Temperature] = {}



    # ------------------------------------------------------------------
    # tariff-related utilities
    # ------------------------------------------------------------------




    @property
    def services(self) -> ScadaAppInterface:
        return typing.cast(ScadaAppInterface, self._services)

    @property
    def settings(self) -> ScadaSettings:
        return self.services.settings

    @property
    def node(self) -> ShNode:
        node = self.layout.node(self.name)
        if node is None:
            raise Exception(f"{self.name} node must exist")
        return node

    @property
    def layout(self) -> HydronicLayout:
        return self.services.hardware_layout

    @property
    def data(self) -> ScadaData:
        return self.services.prime_actor.data

    @property
    def ops(self) -> OperationalParams:
        """The home's authored operational params, of this home's family
        (House0 or Nolan — see sema_to_dc.APPROVED_PAIRS)."""
        return self.data.ops

    def in_onpeak_window(self, at: datetime) -> bool:
        """Whether `at` (wall time in the actor's zone) falls in one of the ops
        word's OnPeakWindows: Start inclusive, End exclusive, on a listed day."""
        day = DayOfWeek[at.strftime("%A")]
        hh_mm = at.strftime("%H:%M")
        return any(
            day in window.Days and window.Start <= hh_mm < window.End
            for window in self.ops.Tariff.OnPeakWindows
        )

    async def await_with_watchdog(
        self,
        total_seconds: float,
        pat_every: float = 20.0,
    ):
        """
        Await for total_seconds, patting the internal watchdog periodically.

        IMPORTANT:
        asyncio.sleep() does NOT pat the watchdog.
        Any awaited duration in LocalControl must go through this helper.
        """
        deadline = time.monotonic() + total_seconds

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            await asyncio.sleep(min(pat_every, remaining))
            self._send(PatInternalWatchdogMessage(src=self.name))

    @property
    def ltn(self) -> ShNode:
        return self.layout.ltn

    @property
    def primary_scada(self) -> ShNode:
        return self.layout.primary_scada

    @property
    def derived_generator(self) -> ShNode:
        return self.layout.derived_generator



    @property
    def pico_cycler(self) -> ShNode:
        return self.layout.nodes[HSNN.pico_cycler]









    ###############################
    # Relay controls
    ################################

    @property
    def layout_type_name(self) -> str:
        """The sema layout word this scada's layout was loaded from
        ("gw.nolan.layout", "house0.layout") — stamped by the loader;
        empty for a legacy runtime-shaped layout file."""
        return self.layout.layout_type_name

    def check_required_nodes(self, names: typing.Sequence[str]) -> None:
        """Fail-fast double-check of an actor's declared REQUIRED_NODES
        list against the layout: every name must resolve, or construction
        crashes (the layout word's axioms should have made this
        impossible)."""
        for name in names:
            self.required_node(name)

    def required_node(self, name: str) -> ShNode:
        """A node the layout contract forces to exist (the layout word's
        axioms guarantee it). A miss means the contract was bypassed —
        Glitch, then crash. Never run partially blind."""
        node = self.layout.node(name)
        if node is None:
            contract = (
                f"a {self.layout_type_name} axiom"
                if self.layout_type_name
                else "the layout contract"
            )
            try:
                self._send_to(
                    self.primary_scada,
                    Glitch(
                        FromGNodeAlias=self.layout.scada_g_node_alias,
                        Node=self.name,
                        Type=LogLevel.Critical,
                        Summary="required-node-missing",
                        Details=(
                            f"{self.name}: required node {name} absent from "
                            f"the layout — {contract} was bypassed"
                        ),
                    ),
                )
            except Exception:  # noqa: BLE001 — the glitch is best-effort;
                pass  # a failed send must never mask the crash
            raise ValueError(
                f"{self.name}: required node {name} absent from layout "
                f"({contract} was bypassed)"
            )
        return node


































    def _send_to(self, dst: ShNode, payload: Any, src: Optional[ShNode] = None) -> None:
        if dst is None:
            return
        if src is None:
            src = self.node
        # HACK FOR nodes whose 'actors' are handled by their parent's communicator
        communicator_by_name = {dst.Name: dst.Name}
        communicator_by_name[CoreNodeNames.local_control_normal] = CoreNodeNames.local_control
        
        message = Message(Src=src.name, Dst=communicator_by_name[dst.Name], Payload=payload)

        if communicator_by_name[dst.name] in set(self.services.get_communicator_names()) | {
            self.name
        }:  # noqa: SLF001
            self.services.send(message)
        elif dst.Name == CoreNodeNames.admin:
            self.services.publish_message(
                link_name=self.services.prime_actor.ADMIN_MQTT,
                message=Message(
                    Src=self.services.publication_name, Dst=dst.Name, Payload=payload
                ),
                qos=QOS.AtMostOnce,
            ) # noqa: SLF001
        elif dst.Name == CoreNodeNames.ltn:
            self.services.publish_upstream(payload)  # noqa: SLF001
        else:
            self.services.publish_message(
                self.services.prime_actor.LOCAL_MQTT, message
            )  # noqa: SLF001

    def log(self, note: str) -> None:
        log_str = f"[{self.name}] {note}"
        self.services.logger.error(log_str)

    ##########################################
    # Data related
    ##########################################

    @property
    def heating_forecast(self) -> HeatingForecast | None:
        return self.data.heating_forecast



    #-----------------------------------------------------------------------
    # Defrost related
    #-----------------------------------------------------------------------


    #-----------------------------------------------------------------------
    # Temperature related
    #-----------------------------------------------------------------------













    


    def channel_temperature(self, channel_name: SpaceheatName) -> Optional[Temperature]:
        """The channel's latest value with the encoding the layout declares
        for it; None when there is no value yet."""
        raw = self.data.latest_channel_values.get(channel_name)
        if raw is None:
            return None
        return self.layout.channel_registry.temperature(channel_name, raw)

    def lwt(self) -> Optional[Temperature]:
        """The latest heat pump leaving water temperature."""
        return self.channel_temperature(HCN.hp_lwt)

    def ewt(self) -> Optional[Temperature]:
        """The latest heat pump entering water temperature."""
        return self.channel_temperature(HCN.hp_ewt)

    def sieg_flow_gpm(self) -> Optional[float]:
        """Returns the latest siegenthaler flow in gallons per minute, or None
        if it does not exist"""
        sieg_x_100 = self.data.latest_channel_values.get(HCN.sieg_flow)
        if sieg_x_100 is None:
            return None
        return sieg_x_100 / 100

    def primary_flow_gpm(self) -> Optional[float]:
        """Returns the latest primary flow in gallons per minute, or None
        if it does not exist"""
        primary_x_100 = self.data.latest_channel_values.get(HCN.primary_flow)
        if primary_x_100 is None:
            return None
        return primary_x_100 / 100

    def lift_f(self) -> Optional[float]:
        """ The lift of the heat pump: leaving water temp minus entering water temp.
        Returns 0 if this is negative (e.g. during defrost). Returns None if missing
        a key temp.
        """
        lwt = self.lwt()
        ewt = self.ewt()
        if lwt is None or ewt is None:
            return None
        return max(0, lwt.f - ewt.f)

    def hottest_store_temp(self) -> Optional[Temperature]:
        """Top of the first store tank; None for a layout without store tanks."""
        if not self.layout.store_tanks:
            return None
        return self.channel_temperature(self.layout.store_tanks[min(self.layout.store_tanks)].depth1)

    def coldest_store_temp(self) -> Optional[Temperature]:
        """Bottom of the last store tank; None for a layout without store tanks."""
        if not self.layout.store_tanks:
            return None
        return self.channel_temperature(self.layout.store_tanks[max(self.layout.store_tanks)].depth3)

    def charge_discharge_relay_state(self) -> StoreFlowRelay:
        """ Returns DischargingStore if relay 3 is de-energized (ISO Valve opened, charge/discharge
        valve in discharge position.) Returns Charging store if energized (ISO Valve closed, charge/discharge
        valve in charge position) """
        sms: SingleMachineState = self.data.latest_machine_state.get(House0NodeNames.store_charge_discharge_relay)
        if sms is None:
            raise Exception("That's strange! Should have a relay state for the charge discharge relay!")
        if sms.StateEnum != StoreFlowRelay.enum_name():
            raise Exception(f"That's strange. Expected StateEnum 'store.flow.relay' but got {sms.StateEnum}")
        return StoreFlowRelay(sms.State)

    def hp_relay_state(self) -> RelayClosedOrOpen:
        sms: SingleMachineState = self.data.latest_machine_state[HSNN.hp_scada_ops_relay]
        if sms is None:
            raise Exception("That's strange! Should have a rela state for the Hp Scada Ops relay!")
        if sms.StateEnum != RelayClosedOrOpen.enum_name():
            raise Exception(f"That's strange. Expected StateEnum 'relay.closed.or.open' but got {sms.StateEnum}")
        return RelayClosedOrOpen(sms.State)

    def alert(self, summary: str, details: str) -> None:
        """Send Critical Glitch """
        self._send_to(self.ltn,
            Glitch(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                Node=self.node.Name,
                Type=LogLevel.Critical,
                Summary=summary,
                Details=details
            )
        )
        self.log(f"Critical Glitch: {summary}")

    def send_warning(self, summary: str, details: str = "") -> None:
        """Send Warning Glitch"""
        self._send_to(self.ltn,
            Glitch(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                Node=self.node.Name,
                Type=LogLevel.Warning,
                Summary=summary,
                Details=details
            )
        )
        self.log(f"Warning Glitch: {summary}")

    def send_error(self, summary: str, details: str = "") -> None:
        """Send Error Glitch"""
        self._send_to(self.ltn,
            Glitch(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                Node=self.node.Name,
                Type=LogLevel.Error,
                Summary=summary,
                Details=details
            )
        )
        self.log(f"Error Glitch: {summary}")

    def send_info(self, summary: str, details: str = "") -> None:
        """Send Info Glitch"""
        self._send_to(self.ltn,
            Glitch(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                Node=self.node.Name,
                Type=LogLevel.Info,
                Summary=summary,
                Details=details
            )
        )
        self.log(f"Info Glitch: {summary}")
