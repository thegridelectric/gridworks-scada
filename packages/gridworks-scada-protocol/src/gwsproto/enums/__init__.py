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

from gwsproto.enums.actor_class import ActorClass
from gwsproto.enums.actuation_authority import ActuationAuthority
from gwsproto.enums.aquastat_control import AquastatControl
from gwsproto.enums.base_g_node_class import BaseGNodeClass
from gwsproto.enums.change_aquastat_control import ChangeAquastatControl
from gwsproto.enums.change_heat_pump_control import ChangeHeatPumpControl
from gwsproto.enums.change_heatcall_source import ChangeHeatcallSource
from gwsproto.enums.change_keep_send import ChangeKeepSend
from gwsproto.enums.change_primary_pump_control import ChangePrimaryPumpControl
from gwsproto.enums.change_relay_pin import ChangeRelayPin
from gwsproto.enums.change_relay_state import ChangeRelayState
from gwsproto.enums.change_store_flow_relay import ChangeStoreFlowRelay
from gwsproto.enums.change_valve_state import ChangeValveState
from gwsproto.enums.change_zone_call_source import ChangeZoneCallSource
from gwsproto.enums.day_of_week import DayOfWeek
from gwsproto.enums.device_type import DeviceType
from gwsproto.enums.emission_method import EmissionMethod
from gwsproto.enums.flow_manifold_variant import FlowManifoldVariant
from gwsproto.enums.fsm_report_type import FsmReportType
from gwsproto.enums.g_node_status import GNodeStatus
from gwsproto.enums.gpio_sense_mode import GpioSenseMode
from gwsproto.enums.gpm_from_hz_method import GpmFromHzMethod
from gwsproto.enums.gw_str_enum import GwStrEnum, SemaEnum
from gwsproto.enums.heat_call_interpretation import HeatCallInterpretation
from gwsproto.enums.heat_pump_control import HeatPumpControl
from gwsproto.enums.heatcall_source import HeatcallSource
from gwsproto.enums.house0_primary_flow_source import House0PrimaryFlowSource
from gwsproto.enums.hp_boss_state import HpBossState
from gwsproto.enums.hp_loop_keep_send import HpLoopKeepSend
from gwsproto.enums.hp_model import HpModel
from gwsproto.enums.hz_calc_method import HzCalcMethod
from gwsproto.enums.i2c_adc_channel import I2cAdcChannel
from gwsproto.enums.i2c_adc_type import I2cAdcType
from gwsproto.enums.i2c_dac_channel import I2cDacChannel
from gwsproto.enums.i2c_dac_type import I2cDacType
from gwsproto.enums.i2c_dac_vref import I2cDacVref
from gwsproto.enums.i2c_mux_type import I2cMuxType
from gwsproto.enums.i2c_operation import I2cOperation
from gwsproto.enums.leaf_ally_all_tanks_event import LeafAllyAllTanksEvent
from gwsproto.enums.leaf_ally_all_tanks_state import LeafAllyAllTanksState
from gwsproto.enums.leaf_ally_buffer_only_event import LeafAllyBufferOnlyEvent
from gwsproto.enums.leaf_ally_buffer_only_state import LeafAllyBufferOnlyState
from gwsproto.enums.local_control_all_tanks_event import LocalControlAllTanksEvent
from gwsproto.enums.local_control_all_tanks_state import LocalControlAllTanksState
from gwsproto.enums.local_control_buffer_only_event import LocalControlBufferOnlyEvent
from gwsproto.enums.local_control_buffer_only_state import LocalControlBufferOnlyState
from gwsproto.enums.local_control_standby_top_event import LocalControlStandbyTopEvent
from gwsproto.enums.local_control_standby_top_state import LocalControlStandbyTopState
from gwsproto.enums.local_control_top_event import LocalControlTopEvent
from gwsproto.enums.local_control_top_state import LocalControlTopState
from gwsproto.enums.log_level import LogLevel
from gwsproto.enums.main_auto_event import MainAutoEvent
from gwsproto.enums.main_auto_state import MainAutoState
from gwsproto.enums.market_price_unit import MarketPriceUnit
from gwsproto.enums.market_quantity_unit import MarketQuantityUnit
from gwsproto.enums.market_type_name import MarketTypeName
from gwsproto.enums.pico_cycler_event import PicoCyclerEvent
from gwsproto.enums.pico_cycler_state import PicoCyclerState
from gwsproto.enums.primary_pump_control import PrimaryPumpControl
from gwsproto.enums.quantity import Quantity
from gwsproto.enums.relay_closed_or_open import RelayClosedOrOpen
from gwsproto.enums.relay_energization_state import RelayEnergizationState
from gwsproto.enums.relay_pin_state import RelayPinState
from gwsproto.enums.relay_wiring_config import RelayWiringConfig
from gwsproto.enums.seasonal_storage_mode import SeasonalStorageMode
from gwsproto.enums.service_mode import ServiceMode
from gwsproto.enums.setpoint_phase import SetpointPhase
from gwsproto.enums.slow_dispatch_contract_status import SlowDispatchContractStatus
from gwsproto.enums.spaceheat_unit import SpaceheatUnit
from gwsproto.enums.store_flow_relay import StoreFlowRelay
from gwsproto.enums.telemetry_name import TelemetryName
from gwsproto.enums.temp_calc_method import TempCalcMethod
from gwsproto.enums.thermistor_data_method import ThermistorDataMethod
from gwsproto.enums.thermostat_kind import ThermostatKind
from gwsproto.enums.top_event import TopEvent
from gwsproto.enums.top_state import TopState
from gwsproto.enums.turn_hp_on_off import TurnHpOnOff
from gwsproto.enums.unit import Unit
from gwsproto.enums.zone_actuator_kind import ZoneActuatorKind
from gwsproto.enums.valve_open_or_closed import ValveOpenOrClosed
from gwsproto.enums.zone_call_circuit_event import ZoneCallCircuitEvent
from gwsproto.enums.zone_call_circuit_state import ZoneCallCircuitState
from gwsproto.enums.zone_call_source import ZoneCallSource
from gwsproto.enums.zone_circuit_governance_event import ZoneCircuitGovernanceEvent
from gwsproto.enums.zone_circuit_governance_state import ZoneCircuitGovernanceState
from gwsproto.enums.zone_circuit_role import ZoneCircuitRole
from gwsproto.enums.zone_setpoint_source import ZoneSetpointSource

__all__ = [
    "ActorClass",
    "ActuationAuthority",
    "AquastatControl",
    "BaseGNodeClass",
    "ChangeAquastatControl",
    "ChangeHeatPumpControl",
    "ChangeHeatcallSource",
    "ChangeKeepSend",
    "ChangePrimaryPumpControl",
    "ChangeRelayPin",
    "ChangeRelayState",
    "ChangeStoreFlowRelay",
    "ChangeValveState",
    "ChangeZoneCallSource",
    "DayOfWeek",
    "DeviceType",
    "EmissionMethod",
    "FlowManifoldVariant",
    "FsmReportType",
    "GNodeStatus",
    "GpioSenseMode",
    "GpmFromHzMethod",
    "GwStrEnum",
    "HeatCallInterpretation",
    "HeatPumpControl",
    "HeatcallSource",
    "House0PrimaryFlowSource",
    "HpBossState",
    "HpLoopKeepSend",
    "HpModel",
    "HzCalcMethod",
    "I2cAdcChannel",
    "I2cAdcType",
    "I2cDacChannel",
    "I2cDacType",
    "I2cDacVref",
    "I2cMuxType",
    "I2cOperation",
    "LeafAllyAllTanksEvent",
    "LeafAllyAllTanksState",
    "LeafAllyBufferOnlyEvent",
    "LeafAllyBufferOnlyState",
    "LocalControlAllTanksEvent",
    "LocalControlAllTanksState",
    "LocalControlBufferOnlyEvent",
    "LocalControlBufferOnlyState",
    "LocalControlStandbyTopEvent",
    "LocalControlStandbyTopState",
    "LocalControlTopEvent",
    "LocalControlTopState",
    "LogLevel",
    "MainAutoEvent",
    "MainAutoState",
    "MarketPriceUnit",
    "MarketQuantityUnit",
    "MarketTypeName",
    "PicoCyclerEvent",
    "PicoCyclerState",
    "PrimaryPumpControl",
    "Quantity",
    "RelayClosedOrOpen",
    "RelayEnergizationState",
    "RelayPinState",
    "RelayWiringConfig",
    "SeasonalStorageMode",
    "SemaEnum",
    "ServiceMode",
    "SetpointPhase",
    "SlowDispatchContractStatus",
    "SpaceheatUnit",
    "StoreFlowRelay",
    "TelemetryName",
    "TempCalcMethod",
    "ThermistorDataMethod",
    "ThermostatKind",
    "TopEvent",
    "TopState",
    "TurnHpOnOff",
    "Unit",
    "ZoneActuatorKind",
    "ValveOpenOrClosed",
    "ZoneCallCircuitEvent",
    "ZoneCallCircuitState",
    "ZoneCallSource",
    "ZoneCircuitGovernanceEvent",
    "ZoneCircuitGovernanceState",
    "ZoneCircuitRole",
    "ZoneSetpointSource",
]
