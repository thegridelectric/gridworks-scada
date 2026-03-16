from __future__ import annotations

from gwsproto.enums import ActorClass, GpioSenseMode, MakeModel, TelemetryName, Unit
from gwsproto.named_types import (
    ChannelConfig,
    ComponentAttributeClassGt,
    Gw108GpioSensorComponentGt,
)
from gwsproto.names.hydronic_spaceheat.helpers import ZoneNodeNames, ZoneChannelNames

from layout_gen.layout_db import LayoutDb  # <- adjust
from layout_gen.base_layout_gen import (
    add_spaceheat_node, 
    add_data_channel,
    add_heat_call_derived_channel,
    ZoneWhitewireNames
)

DERIVED_GENERATOR_NODE_NAME = "derived-generator"

GW108_WHITEWIRE_GPIO_PINS = {
    1: 17,
    2: 27,
    3: 22,
    4: 10,
    5: 9,
    6: 11,
}

GW108_DEVICE_ID = "8ad2f6fe-e834-4334-80c8-4a0d4ef4b04f"

def ensure_gw108_device(db: LayoutDb) -> None:
    if GW108_DEVICE_ID in db.cacs_by_id:
        return

    db.add_cacs(
        [
            ComponentAttributeClassGt(
                ComponentAttributeClassId=GW108_DEVICE_ID,
                MakeModel=MakeModel.GRIDWORKS__SCADA_GW108,
                DisplayName="GridWorks SCADA Gw108",
            )
        ],
        "OtherCacs",
    )


def add_gw108_gpio_sensor(
    db: LayoutDb,
    *,
    about_node_name: str,
    sensor_node_name: str,
    data_channel_name: str,
    gpio_pin: int,
    component_display_name: str,
    sensor_node_display_name: str,
    data_channel_display_name: str,
    terminal_asset_alias: str,
    poll_period_ms: int = 1000,
    capture_period_s: int = 300,
    async_capture_delta: int = 1,
) -> None:
    """
    Ensures Gw108 Device exists and then adds:
      - GW108 GPIO sensor component (SendToDerived=True)
      - sensor ShNode (ActorClass=GpioSensor)
      - DataChannel (Unitless)
    """

    ensure_gw108_device(db)
    component_id = db.make_component_id(component_display_name)

    component = Gw108GpioSensorComponentGt(
        ComponentAttributeClassId=GW108_DEVICE_ID,
        ComponentId=component_id,
        DisplayName=component_display_name,
        GpioPin=gpio_pin,
        SenseMode=GpioSenseMode.Polling,
        SendToDerived=True,
        ConfigList=[ 
            ChannelConfig(
                ChannelName=data_channel_name,
                PollPeriodMs=poll_period_ms,
                CapturePeriodS=capture_period_s,
                AsyncCapture=True,
                AsyncCaptureDelta=async_capture_delta,
                Exponent=0,
                Unit=Unit.Unitless
            )
        ],
    )

    db.add_components([component], layout_list_name="OtherComponents")

    add_spaceheat_node(
        db,
        name=sensor_node_name,
        actor_class=ActorClass.GpioSensor,
        display_name=sensor_node_display_name,
        component_id=component_id,
    )

    add_data_channel(
        db,
        name=data_channel_name,
        about_node_name=about_node_name,
        captured_by_node_name=sensor_node_name,
        display_name=data_channel_display_name,
        telemetry_name=TelemetryName.Unknown,
        terminal_asset_alias=terminal_asset_alias,
    )


def add_whitewire_zone(
    db: LayoutDb,
    *,
    node_names: ZoneNodeNames,
    channel_names: ZoneChannelNames,
    gpio_pin: int,
    terminal_asset_alias: str,
) -> None:
    """
    Adds the whitewire opto sensing stack for a zone:

      - gw108.gpio.sensor.component.gt
      - GpioSensor node
      - DataChannel (zoneX-*-opto-input)
      - Derived heat-call channel (zoneX-*-heat-call)
    """

    zone_display = names.display_zone

    add_spaceheat_node(
        db,
        name=names.zone_node,
        actor_class=ActorClass.NoActor,
        display_name=f"Zone {names.idx} {zone_display}",
    )

    add_gw108_gpio_sensor(
        db,
        about_node_name=names.zone_node,
        sensor_node_name=names.whitewire_sensor_node,
        data_channel_name=names.whitewire_data_channel,
        gpio_pin=gpio_pin,
        component_display_name=f"{names.zone_display_prefix} Whitewire Optocoupler",
        sensor_node_display_name=f"{names.zone_display_prefix} Opto Input",
        data_channel_display_name=f"{names.zone_display_prefix} Opto Input",
        terminal_asset_alias=terminal_asset_alias,
    )


    add_heat_call_derived_channel(
        db,
        name=names.heat_call_channel,
        created_by_node_name=DERIVED_GENERATOR_NODE_NAME,
        input_channel_name=names.whitewire_data_channel,
        display_name=f"Zone {names.idx} {zone_display} Heat Call",
        terminal_asset_alias=terminal_asset_alias,
    )