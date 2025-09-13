from typing import Self

from gwproto.enums import ActorClass
from gwproto.enums import MakeModel
from gwproto.enums import TelemetryName
from gwproto.enums import Unit
from gwproto.named_types import ComponentAttributeClassGt
from gwproto.named_types import HubitatPollerComponentGt
from gwproto.type_helpers import CACS_BY_MAKE_MODEL
from gwproto.type_helpers import HubitatPollerGt
from gwproto.type_helpers import MakerAPIAttributeGt
from gwproto.named_types import SpaceheatNodeGt
from gwproto.named_types import DataChannelGt
from gwproto.named_types.hubitat_gt import HubitatGt
from gwproto.named_types import ChannelConfig
from pydantic import BaseModel
from gwsproto.data_classes.house_0_names import H0N
from layout_gen import LayoutDb
from layout_gen.hubitat import add_hubitat

HUBITAT_MIN_POLL_S = 5
TEMP_CHANNEL_SUFFIX = "temp"
SETPT_CHANNEL_SUFFIX = "set"
STATE_CHANNEL_SUFFIX = "state"
HUBITAT_TEMP_ATTRIBUTE_NAME = "temperature"
HUBITAT_SETPT_ATTRIBUTE_NAME = "heatingSetpoint"
HUBITAT_STATE_ATTRIBUTE_NAME = "thermostatOperatingState"

class HubitatThermostatGenCfg(BaseModel):
    zone_idx: int
    zone_name: str
    hubitat: HubitatGt
    device_id: int
    capture_period_seconds: float = 300
    enabled: bool = True
    web_poll_enabled: bool = True
    web_listen_enabled: bool = True
    actor_class: ActorClass = ActorClass.HoneywellThermostat

def add_thermostat(
    db: LayoutDb,
    stat_cfg: HubitatThermostatGenCfg,
) -> None:
    hubitat_alias = add_hubitat(db, stat_cfg.hubitat)
    make_model = MakeModel.HONEYWELL__T6ZWAVETHERMOSTAT
    if not db.cac_id_by_alias(make_model):
        db.add_cacs(
            [
                ComponentAttributeClassGt(
                    ComponentAttributeClassId=CACS_BY_MAKE_MODEL[make_model],
                    DisplayName="Honeywell T6 Thermostat",
                    MakeModel=make_model,
                    MinPollPeriodMs=HUBITAT_MIN_POLL_S * 1000,
                ),
            ]
        )
    stat_component_display_name = f"Thermostat {stat_cfg.zone_idx} for {stat_cfg.zone_name}"
    temp_channel_name = f"zone{stat_cfg.zone_idx}-{stat_cfg.zone_name}-{TEMP_CHANNEL_SUFFIX}"
    setpt_channel_name = f"zone{stat_cfg.zone_idx}-{stat_cfg.zone_name}-{SETPT_CHANNEL_SUFFIX}"
    state_channel_name = f"zone{stat_cfg.zone_idx}-{stat_cfg.zone_name}-{STATE_CHANNEL_SUFFIX}"
    zone_node_name = f"zone{stat_cfg.zone_idx}-{stat_cfg.zone_name}"
    stat_node_name = f"zone{stat_cfg.zone_idx}-{stat_cfg.zone_name}-stat"
    db.add_components(
        [
            HubitatPollerComponentGt(
                ComponentId=db.make_component_id(stat_component_display_name),
                ComponentAttributeClassId=db.cac_id_by_alias(make_model),
                DisplayName=stat_component_display_name, 
                Poller=HubitatPollerGt(
                    hubitat_component_id=db.component_id_by_alias(hubitat_alias),
                    device_id=stat_cfg.device_id,
                    attributes=[
                        MakerAPIAttributeGt(
                        attribute_name=HUBITAT_TEMP_ATTRIBUTE_NAME,
                        node_name=zone_node_name,
                        channel_name=temp_channel_name,
                        telemetry_name=TelemetryName.AirTempFTimes1000,
                        unit=Unit.Fahrenheit,
                        web_poll_enabled=stat_cfg.web_poll_enabled,
                        web_listen_enabled=stat_cfg.web_listen_enabled,
                    ),
                    MakerAPIAttributeGt(
                        attribute_name=HUBITAT_SETPT_ATTRIBUTE_NAME,
                        node_name=stat_node_name,
                        channel_name=setpt_channel_name,
                        telemetry_name=TelemetryName.AirTempFTimes1000,
                        unit=Unit.Fahrenheit,
                        web_poll_enabled=stat_cfg.web_poll_enabled,
                        web_listen_enabled=stat_cfg.web_listen_enabled,
                    ),
                    MakerAPIAttributeGt(
                        attribute_name=HUBITAT_STATE_ATTRIBUTE_NAME,
                        node_name=zone_node_name,
                        channel_name=state_channel_name,
                        interpret_as_number=False,
                        telemetry_name=TelemetryName.ThermostatState,
                        unit=Unit.Unitless,
                        web_poll_enabled=stat_cfg.web_poll_enabled,
                        web_listen_enabled=stat_cfg.web_listen_enabled,
                    ),
                    ],
                    enabled=stat_cfg.enabled,
                    poll_period_seconds=stat_cfg.capture_period_seconds,
                ),
                ConfigList=[
                    ChannelConfig(
                        ChannelName=temp_channel_name,
                        PollPeriodMs=HUBITAT_MIN_POLL_S * 1000,
                        CapturePeriodS=stat_cfg.capture_period_seconds,
                        AsyncCapture=True,
                        AsyncCaptureDelta=1,
                        Exponent=3,
                        Unit=Unit.Fahrenheit
                    ),
                    ChannelConfig(
                        ChannelName=setpt_channel_name,
                        PollPeriodMs=HUBITAT_MIN_POLL_S * 1000,
                        CapturePeriodS=stat_cfg.capture_period_seconds,
                        AsyncCapture=False,
                        Exponent=3,
                        Unit=Unit.Fahrenheit
                    ),
                    ChannelConfig(
                        ChannelName=state_channel_name,
                        PollPeriodMs=HUBITAT_MIN_POLL_S * 1000,
                        CapturePeriodS=stat_cfg.capture_period_seconds,
                        AsyncCapture=True,
                        AsyncCaptureDelta=1,
                        Exponent=0,
                        Unit=Unit.ThermostatStateEnum,
                    )
                ]
            )
        ]
    )

    stat_display_name = f"Zone {stat_cfg.zone_idx} {stat_cfg.zone_name.capitalize()} Thermostat"
    zone_display_name = f"Zone {stat_cfg.zone_idx} {stat_cfg.zone_name.capitalize()}"
    db.add_nodes(
        [
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(stat_node_name),
                Name=stat_node_name,
                ActorHierarchyName=f"{H0N.secondary_scada}.{stat_node_name}",
                ActorClass=stat_cfg.actor_class,
                DisplayName=stat_display_name,
                ComponentId=db.component_id_by_alias(stat_component_display_name)
            )
        ] + [
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(zone_node_name),
                Name=zone_node_name,
                ActorClass=ActorClass.NoActor,
                DisplayName=zone_display_name,
            )
        ]
    )
    db.add_data_channels(
        [
            DataChannelGt(
                Name= temp_channel_name,
                DisplayName = ' '.join(word.capitalize() for word in temp_channel_name.split('-')),
                AboutNodeName=zone_node_name,
                CapturedByNodeName=stat_node_name,
                TelemetryName=TelemetryName.AirTempFTimes1000,
                TerminalAssetAlias=db.terminal_asset_alias,
                Id = db.make_channel_id(temp_channel_name)
            ),
            DataChannelGt(
                Name=setpt_channel_name,
                DisplayName = ' '.join(word.capitalize() for word in setpt_channel_name.split('-')),
                AboutNodeName=stat_node_name,
                CapturedByNodeName=stat_node_name,
                TelemetryName=TelemetryName.AirTempFTimes1000,
                TerminalAssetAlias=db.terminal_asset_alias,
                Id = db.make_channel_id(setpt_channel_name)
            ),
            DataChannelGt(
                Name=state_channel_name,
                DisplayName = ' '.join(word.capitalize() for word in state_channel_name.split('-')),
                AboutNodeName=stat_node_name,
                CapturedByNodeName=stat_node_name,
                TelemetryName=TelemetryName.ThermostatState,
                TerminalAssetAlias=db.terminal_asset_alias,
                Id = db.make_channel_id(state_channel_name)
            ),
        ]
    )