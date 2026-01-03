"""
GridWorks Enums used in scada, the Application Shared Language (ASL) used by SCADA
devices and AtomicTNodes to communicate with each other. These enums play a specific structural
role as semantic "glue" within ASLs.

Application Shared Languages are an evolution of the concept of Application Programming Interfaces.
In a nutshell, an API can be viewed as a rather restricted version of an SAL, where only one application
has anything complex/interesting to say and, in general, the developers/owners of that application
have sole responsibility for managing the versioning and changing of that API. Note also that SALs
do not make any a priori assumption about the relationship (i.e. the default client/server for an API)
or the message delivery mechanism (i.e. via default GET/POST to RESTful URLs). For more information
on these ideas:
  - [GridWorks Enums](https://gridwork-type-registry.readthedocs.io/en/latest/types.html)
  - [GridWorks Types](https://gridwork-type-registry.readthedocs.io/en/latest/types.html)
  - [ASLs](https://gridwork-type-registry.readthedocs.io/en/latest/asls.html)
 """

from gw.enums import MarketTypeName
from gwsproto.enums.aa_buffer_only_event import AaBufferOnlyEvent
from gwsproto.enums.aa_buffer_only_state import AaBufferOnlyState
from gwsproto.enums.actor_class import ActorClass
from gwsproto.enums.atomic_ally_event import AtomicAllyEvent
from gwsproto.enums.atomic_ally_state import AtomicAllyState
from gwsproto.enums.aquastat_control import AquastatControl
from gwsproto.enums.contract_status import ContractStatus
from gwsproto.enums.change_aquastat_control import ChangeAquastatControl
from gwsproto.enums.change_heatcall_source import ChangeHeatcallSource
from gwsproto.enums.change_heat_pump_control import ChangeHeatPumpControl
from gwsproto.enums.change_primary_pump_control import ChangePrimaryPumpControl
from gwsproto.enums.change_keep_send import ChangeKeepSend
from gwsproto.enums.change_relay_pin import ChangeRelayPin
from gwsproto.enums.change_relay_state import ChangeRelayState
from gwsproto.enums.change_store_flow_relay import ChangeStoreFlowRelay
from gwsproto.enums.flow_manifold_variant import FlowManifoldVariant
from gwsproto.enums.fsm_action_type import FsmActionType
from gwsproto.enums.fsm_report_type import FsmReportType
from gwsproto.enums.gpm_from_hz_method import GpmFromHzMethod
from gwsproto.enums.heatcall_source import HeatcallSource
from gwsproto.enums.heat_pump_control import HeatPumpControl
from gwsproto.enums.home_alone_strategy import HomeAloneStrategy
from gwsproto.enums.hz_calc_method import HzCalcMethod
from gwsproto.enums.local_control_top_state import LocalControlTopState
from gwsproto.enums.gw_unit import GwUnit
from gwsproto.enums.hp_model import HpModel
from gwsproto.enums.hp_loop_keep_send import HpLoopKeepSend
from gwsproto.enums.local_control_top_state_event import LocalControlTopStateEvent
from gwsproto.enums.log_level import LogLevel
from gwsproto.enums.main_auto_event import MainAutoEvent
from gwsproto.enums.main_auto_state import MainAutoState
from gwsproto.enums.make_model import MakeModel
from gwsproto.enums.market_price_unit import MarketPriceUnit
from gwsproto.enums.market_quantity_unit import MarketQuantityUnit
from gwsproto.enums.pico_cycler_event import PicoCyclerEvent
from gwsproto.enums.pico_cycler_state import PicoCyclerState
from gwsproto.enums.primary_pump_control import PrimaryPumpControl
from gwsproto.enums.relay_closed_or_open import RelayClosedOrOpen
from gwsproto.enums.relay_energization_state import RelayEnergizationState
from gwsproto.enums.relay_wiring_config import RelayWiringConfig
from gwsproto.enums.store_flow_relay import StoreFlowRelay
from gwsproto.enums.telemetry_name import TelemetryName
from gwsproto.enums.temp_calc_method import TempCalcMethod
from gwsproto.enums.thermistor_data_method import ThermistorDataMethod
from gwsproto.enums.top_event import TopEvent
from gwsproto.enums.top_state import TopState
from gwsproto.enums.turn_hp_on_off import TurnHpOnOff
from gwsproto.enums.unit import Unit


__all__ = [
    "AaBufferOnlyEvent",
    "AaBufferOnlyState",
    "ActorClass",
    "AtomicAllyEvent",
    "AtomicAllyState",
    "AquastatControl",
    "ChangeAquastatControl",
    "ChangeHeatPumpControl",
    "ChangeHeatcallSource", 
    "ChangeKeepSend",
    "ChangePrimaryPumpControl",
    "ChangeRelayPin",
    "ChangeRelayState",
    "ChangeStoreFlowRelay",
    "ContractStatus",
    "FlowManifoldVariant",
    "FsmActionType",
    "FsmReportType",
    "GpmFromHzMethod",
    "GwUnit",
    "HeatcallSource",
    "HeatPumpControl",
    "HomeAloneStrategy",
    "HpModel",
    "HzCalcMethod",
    "LocalControlTopState",
    "HpLoopKeepSend",
    "LogLevel",
    "LocalControlTopStateEvent",  
    "MainAutoEvent",
    "MainAutoState",
    "MakeModel",
    "MarketPriceUnit",
    "MarketQuantityUnit",
    "MarketTypeName",
    "PicoCyclerEvent",
    "PicoCyclerState",
    "PrimaryPumpControl",
    "RelayClosedOrOpen",
    "RelayEnergizationState",
    "RelayWiringConfig",
    "StoreFlowRelay",
    "TelemetryName",
    "TempCalcMethod",
    "ThermistorDataMethod",
    "TopEvent",
    "TopState",
    "TurnHpOnOff",
    "Unit",
]
