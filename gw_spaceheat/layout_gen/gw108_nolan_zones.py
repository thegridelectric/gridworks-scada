"""GW108 hardware implementation of Nolan thermostat zones.

Builds the per-zone Spaceheat nodes, components, and data channels for a
Nolan-strategy layout running on the GW108 board: an optocoupler GpioSensor on
each zone's thermostat whitewire, plus a shared ADS1115 thermistor reader that
measures each zone's GW temperature.
"""
from typing import Sequence

from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import (
    ActorClass,
    GpioSenseMode,
    DeviceType,
    Quantity,
    TelemetryName,
    TempCalcMethod,
    Unit,
)
from gwsproto.named_types import (
    ChannelConfig,
    ScadaDeviceTypeGt,
    DataChannelGt,
    Gw108GpioSensorComponentGt,
    I2cThermistorChannelConfig,
    I2cThermistorReaderComponentGt,
    SpaceheatNodeGt,
)
from gwsproto.names.hydronic_spaceheat.channel_names import (
    HydronicSpaceheatZoneChannelNames as HSZoneChannelNames,
)
from gwsproto.names.hydronic_spaceheat.node_names import (
    HydronicSpaceheatZoneNodeNames as HSZoneNodeNames,
)
from gwsproto.names.nolan.channel_names import NolanZoneChannelNames
from gwsproto.names.nolan.node_names import NolanZoneNodeNames

from layout_gen.layout_db import LayoutDb

GW108_THERMISTOR_READER = "gw108-thermistor-reader"

# The current GW108 board rev exposes a single ADS1115 thermistor ADC at i2c
# address 0x49 (73 decimal), with 4 channels P0-P3. A future board rev will add
# a second i2c address; _zone_thermistor_configs is the single place that
# decision lives.
GW108_ADC_ADDRESS = 73
_ADS1115_CHANNELS = ["P0", "P1", "P2", "P3"]
_THERMISTOR_BETA = 3977

# BCM GPIO pins for per-zone optocoupler inputs on the GW108 board.
_OPTO_GPIO_PINS = [17, 27, 22, 10]


def _zone_thermistor_configs(
    zone_idx: int,
    gw_temp_channel: str,
    gw_microvolts_channel: str,
    adc_address: int = GW108_ADC_ADDRESS,
) -> tuple[int, list[I2cThermistorChannelConfig]]:
    """Return (AdcAddress, [gw-temp config, gw-microvolts config]) for a zone.

    Both configs read the same ADS1115 channel: one decoded as Celsius (x100),
    one as the raw microvolt reading. The current GW108 rev has only the 0x49
    ADC, so this insists AdcAddress == GW108_ADC_ADDRESS; the two-address board
    rev will relax that here.
    """
    if adc_address != GW108_ADC_ADDRESS:
        raise ValueError(
            f"GW108 currently has a single thermistor ADC at i2c address "
            f"{GW108_ADC_ADDRESS} (0x49); a two-address board rev is needed "
            f"before AdcAddress {adc_address} can be used"
        )
    if zone_idx > len(_ADS1115_CHANNELS):
        raise ValueError(
            f"GW108 thermistor reader has {len(_ADS1115_CHANNELS)} ADC channels "
            f"(one ADS1115 at 0x49); zone {zone_idx} is out of range"
        )
    adc_channel = _ADS1115_CHANNELS[zone_idx - 1]
    return adc_address, [
        I2cThermistorChannelConfig(
            ChannelName=gw_temp_channel,
            AdcChannel=adc_channel,
            ThermistorBeta=_THERMISTOR_BETA,
            PollPeriodMs=1000,
            CapturePeriodS=60,
            AsyncCapture=True,
            AsyncCaptureDelta=50,
            Exponent=2,
            Unit=Unit.Celcius,
            SendToDerived=True,
        ),
        I2cThermistorChannelConfig(
            ChannelName=gw_microvolts_channel,
            AdcChannel=adc_channel,
            ThermistorBeta=_THERMISTOR_BETA,
            PollPeriodMs=1000,
            CapturePeriodS=60,
            AsyncCapture=True,
            AsyncCaptureDelta=5000,
            Exponent=6,
            Unit=Unit.VoltsRms,
        ),
    ]


def add_gw108_nolan_zones(
    db: LayoutDb,
    *,
    zone_idxs: Sequence[int] | None = None,
) -> None:
    """GW108 hardware implementation of Nolan thermostat zones.

    Per zone in db.misc["ZoneList"]: zone + whitewire (NoActor) nodes, an opto
    GpioSensor node + Gw108GpioSensorComponentGt, and opto-input / gw-temp /
    gw-microvolts data channels. All zones share one gw108-thermistor-reader
    node + I2cThermistorReaderComponentGt, with zone i mapped to ADS1115
    channel P{i-1}. Requires len(ZoneList) <= 4.
    """
    zone_list = db.misc["ZoneList"]
    if zone_idxs is None:
        zone_idxs = range(1, len(zone_list) + 1)
    if max(zone_idxs) > len(_ADS1115_CHANNELS):
        raise ValueError(
            f"GW108 thermistor reader supports at most {len(_ADS1115_CHANNELS)} "
            f"zones (one ADS1115 at 0x49); got zone {max(zone_idxs)}"
        )

    if not db.has_device_type_record(DeviceType.GridworksScadaGw108):
        db.add_device_types(
            [
                ScadaDeviceTypeGt(
                    DeviceType=DeviceType.GridworksScadaGw108,
                    DisplayName="GridWorks SCADA Gw108",
                ),
            ]
        )

    nodes_to_add: list[SpaceheatNodeGt] = []
    data_channels: list[DataChannelGt] = []
    thermistor_configs: list[I2cThermistorChannelConfig] = []
    adc_addresses: set[int] = set()

    for zone_idx in zone_idxs:
        zone_name = zone_list[zone_idx - 1]
        zone_nodes = HSZoneNodeNames(zone_name, zone_idx)
        nolan_nodes = NolanZoneNodeNames(zone_name, zone_idx)
        zone_channels = NolanZoneChannelNames(zone_name, zone_idx)
        hs_channels = HSZoneChannelNames(zone_name, zone_idx)
        zone_title = zone_name.replace("-", " ").title()

        # zone + whitewire structural (NoActor) nodes
        for node_name, display_name in [
            (zone_nodes.zone, f"Zone {zone_idx} {zone_title}"),
            (zone_nodes.whitewire, f"Zone {zone_idx} {zone_title} Whitewire"),
        ]:
            if not db.node_id_by_name(node_name):
                nodes_to_add.append(
                    SpaceheatNodeGt(
                        ShNodeId=db.make_node_id(node_name),
                        Name=node_name,
                        ActorClass=ActorClass.NoActor,
                        DisplayName=display_name,
                    )
                )

        # opto GpioSensor: one Gw108GpioSensorComponentGt per zone
        opto_component_name = f"Zone {zone_idx} {zone_title} Opto Component"
        if not db.component_id_by_alias(opto_component_name):
            db.add_components(
                [
                    Gw108GpioSensorComponentGt(
                        ComponentId=db.make_component_id(opto_component_name),
                        DeviceType=DeviceType.GridworksScadaGw108,
                        DisplayName=opto_component_name,
                        GpioPin=_OPTO_GPIO_PINS[zone_idx - 1],
                        SenseMode=GpioSenseMode.Polling,
                        SendToDerived=True,
                        ConfigList=[
                            ChannelConfig(
                                ChannelName=zone_channels.opto_input,
                                PollPeriodMs=1000,
                                CapturePeriodS=300,
                                AsyncCapture=True,
                                AsyncCaptureDelta=1,
                                Exponent=0,
                                Unit=Unit.Unitless,
                            ),
                        ],
                    )
                ]
            )
        if not db.node_id_by_name(nolan_nodes.opto):
            nodes_to_add.append(
                SpaceheatNodeGt(
                    ShNodeId=db.make_node_id(nolan_nodes.opto),
                    Name=nolan_nodes.opto,
                    ActorHierarchyName=f"{H0N.primary_scada}.{nolan_nodes.opto}",
                    ActorClass=ActorClass.GpioSensor,
                    DisplayName=f"Zone {zone_idx} {zone_title} Opto",
                    ComponentId=db.component_id_by_alias(opto_component_name),
                )
            )

        # thermistor configs for this zone's shared ADS1115 channel
        adc_address, zone_thermistor_configs = _zone_thermistor_configs(
            zone_idx,
            zone_channels.gw_temp,
            hs_channels.gw_microvolts,
        )
        adc_addresses.add(adc_address)
        thermistor_configs.extend(zone_thermistor_configs)

        data_channels.extend(
            [
                DataChannelGt(
                    Name=zone_channels.opto_input,
                    DisplayName=f"Zone {zone_idx} {zone_title} Opto Input",
                    AboutNodeName=zone_nodes.whitewire,
                    CapturedByNodeName=nolan_nodes.opto,
                    TelemetryName=TelemetryName.BinaryState,
                    Quantity=Quantity.Unitless,
                    TerminalAssetAlias=db.terminal_asset_alias,
                    Id=db.make_channel_id(zone_channels.opto_input),
                ),
                DataChannelGt(
                    Name=zone_channels.gw_temp,
                    DisplayName=f"Zone {zone_idx} {zone_title} GW Temp",
                    AboutNodeName=zone_nodes.zone,
                    CapturedByNodeName=GW108_THERMISTOR_READER,
                    TelemetryName=TelemetryName.CelsiusTimes100,
                    Quantity=Quantity.Temperature,
                    TerminalAssetAlias=db.terminal_asset_alias,
                    Id=db.make_channel_id(zone_channels.gw_temp),
                ),
                DataChannelGt(
                    Name=hs_channels.gw_microvolts,
                    DisplayName=f"Zone {zone_idx} {zone_title} GW Microvolts",
                    AboutNodeName=zone_nodes.zone,
                    CapturedByNodeName=GW108_THERMISTOR_READER,
                    TelemetryName=TelemetryName.MicroVolts,
                    Quantity=Quantity.Voltage,
                    TerminalAssetAlias=db.terminal_asset_alias,
                    Id=db.make_channel_id(hs_channels.gw_microvolts),
                ),
            ]
        )

    # All zones share a single GW108 thermistor reader (one i2c address today).
    if len(adc_addresses) != 1:
        raise ValueError(
            f"GW108 currently supports a single thermistor ADC address; "
            f"got {sorted(adc_addresses)}"
        )
    reader_component_name = "GW108 Thermistor Reader"
    if not db.component_id_by_alias(reader_component_name):
        db.add_components(
            [
                I2cThermistorReaderComponentGt(
                    ComponentId=db.make_component_id(reader_component_name),
                    DeviceType=DeviceType.GridworksScadaGw108,
                    DisplayName=reader_component_name,
                    Bus="i2c-1",
                    AdcAddress=adc_addresses.pop(),
                    AdcReferenceVolts=3.3,
                    SeriesResistanceKOhms=5.6,
                    TempCalcMethod=TempCalcMethod.SimpleBeta,
                    ConfigList=thermistor_configs,
                )
            ]
        )
    if not db.node_id_by_name(GW108_THERMISTOR_READER):
        nodes_to_add.append(
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(GW108_THERMISTOR_READER),
                Name=GW108_THERMISTOR_READER,
                ActorHierarchyName=f"{H0N.primary_scada}.{GW108_THERMISTOR_READER}",
                ActorClass=ActorClass.I2cThermistorReader,
                DisplayName="GW108 Thermistor Reader",
                ComponentId=db.component_id_by_alias(reader_component_name),
            )
        )

    if nodes_to_add:
        db.add_nodes(nodes_to_add)
    db.add_data_channels(data_channels)
