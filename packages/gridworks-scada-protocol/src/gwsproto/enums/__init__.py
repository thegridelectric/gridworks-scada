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

from gwsproto.enums.gw_str_enum import GwStrEnum, AslEnum
from gwsproto.enums.actor_class import ActorClass
from gwsproto.enums.aquastat_control import AquastatControl
from gwsproto.enums.change_aquastat_control import ChangeAquastatControl
from gwsproto.enums.change_heatcall_source import ChangeHeatcallSource
from gwsproto.enums.change_heat_pump_control import ChangeHeatPumpControl
from gwsproto.enums.change_primary_pump_control import ChangePrimaryPumpControl
from gwsproto.enums.change_keep_send import ChangeKeepSend
from gwsproto.enums.change_relay_pin import ChangeRelayPin
from gwsproto.enums.change_relay_state import ChangeRelayState
from gwsproto.enums.change_store_flow_relay import ChangeStoreFlowRelay
from gwsproto.enums.emission_method import EmissionMethod
from gwsproto.enums.flow_manifold_variant import FlowManifoldVariant
from gwsproto.enums.fsm_report_type import FsmReportType
from gwsproto.enums.gpm_from_hz_method import GpmFromHzMethod
from gwsproto.enums.heat_call_interpretation import HeatCallInterpretation
from gwsproto.enums.heatcall_source import HeatcallSource
from gwsproto.enums.heat_pump_control import HeatPumpControl
from gwsproto.enums.hp_boss_state import HpBossState
from gwsproto.enums.hz_calc_method import HzCalcMethod
from gwsproto.enums.leaf_ally_buffer_only_event import LeafAllyBufferOnlyEvent
from gwsproto.enums.leaf_ally_buffer_only_state import LeafAllyBufferOnlyState
from gwsproto.enums.leaf_ally_all_tanks_event import LeafAllyAllTanksEvent
from gwsproto.enums.leaf_ally_all_tanks_state import LeafAllyAllTanksState
from gwsproto.enums.local_control_buffer_only_event import LocalControlBufferOnlyEvent
from gwsproto.enums.local_control_buffer_only_state import LocalControlBufferOnlyState
from gwsproto.enums.local_control_all_tanks_event import LocalControlAllTanksEvent
from gwsproto.enums.local_control_all_tanks_state import LocalControlAllTanksState
from gwsproto.enums.local_control_standby_top_event import LocalControlStandbyTopEvent
from gwsproto.enums.local_control_standby_top_state import LocalControlStandbyTopState
from gwsproto.enums.local_control_top_state import LocalControlTopState
from gwsproto.enums.local_control_top_event import LocalControlTopEvent
from gwsproto.enums.gpio_sense_mode import GpioSenseMode
from gwsproto.enums.gw_unit import GwUnit
from gwsproto.enums.hp_model import HpModel
from gwsproto.enums.hp_loop_keep_send import HpLoopKeepSend
from gwsproto.enums.log_level import LogLevel
from gwsproto.enums.main_auto_event import MainAutoEvent
from gwsproto.enums.main_auto_state import MainAutoState
from gwsproto.enums.make_model import MakeModel
from gwsproto.enums.market_price_unit import MarketPriceUnit
from gwsproto.enums.market_quantity_unit import MarketQuantityUnit
from gwsproto.enums.market_type_name import MarketTypeName
from gwsproto.enums.pico_cycler_event import PicoCyclerEvent
from gwsproto.enums.pico_cycler_state import PicoCyclerState
from gwsproto.enums.primary_pump_control import PrimaryPumpControl
from gwsproto.enums.relay_closed_or_open import RelayClosedOrOpen
from gwsproto.enums.relay_pin_state import RelayPinState
from gwsproto.enums.relay_energization_state import RelayEnergizationState
from gwsproto.enums.relay_wiring_config import RelayWiringConfig
from gwsproto.enums.seasonal_storage_mode import SeasonalStorageMode
from gwsproto.enums.slow_dispatch_contract_status import SlowDispatchContractStatus
from gwsproto.enums.store_flow_relay import StoreFlowRelay
from gwsproto.enums.system_mode import SystemMode
from gwsproto.enums.telemetry_name import TelemetryName
from gwsproto.enums.temp_calc_method import TempCalcMethod
from gwsproto.enums.thermistor_data_method import ThermistorDataMethod
from gwsproto.enums.top_event import TopEvent
from gwsproto.enums.top_state import TopState
from gwsproto.enums.turn_hp_on_off import TurnHpOnOff
from gwsproto.enums.unit import Unit


__all__ = [
    "AslEnum",
    "GwStrEnum",
    "ActorClass",
    "AquastatControl",
    "ChangeAquastatControl",
    "ChangeHeatPumpControl",
    "ChangeHeatcallSource", 
    "ChangeKeepSend",
    "ChangePrimaryPumpControl",
    "ChangeRelayPin",
    "ChangeRelayState",
    "ChangeStoreFlowRelay",
    "EmissionMethod",
    "FlowManifoldVariant",
    "FsmReportType",
    "GpioSenseMode",
    "GpmFromHzMethod",
    "GwUnit",
    "HeatCallInterpretation",
    "HeatcallSource",
    "HeatPumpControl",
    "HpBossState",
    "HpModel",
    "HzCalcMethod",
    "LocalControlTopState",
    "HpLoopKeepSend",
    "LeafAllyBufferOnlyEvent",
    "LeafAllyBufferOnlyState",
    "LeafAllyAllTanksEvent",
    "LeafAllyAllTanksState",
    "LocalControlBufferOnlyEvent",
    "LocalControlBufferOnlyState",
    "LocalControlStandbyTopEvent",
    "LocalControlStandbyTopState",
    "LocalControlAllTanksEvent",
    "LocalControlAllTanksState",
    "LogLevel",
    "LocalControlTopEvent",  
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
    "RelayPinState",
    "RelayWiringConfig",
    "SeasonalStorageMode",
    "SlowDispatchContractStatus",
    "StoreFlowRelay",
    "SystemMode",
    "TelemetryName",
    "TempCalcMethod",
    "ThermistorDataMethod",
    "TopEvent",
    "TopState",
    "TurnHpOnOff",
    "Unit",
]
