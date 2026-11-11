"""The thermistors of a scada board's ADC, as their reader's actor reads
them. Where the ADC sits and what it is wired to is resolved once from the
board's device-type record, and the conversion from the ADC's volts to a
temperature is made here: the reader's actor holds none of it.
"""

import asyncio
import math
import uuid
from typing import Any, NamedTuple

from gwsproto.data_classes.components import I2cThermistorReaderComponent
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import TelemetryName, TempCalcMethod
from gwsproto.named_types import (
    I2cReadReg,
    I2cRegAddress,
    I2cThermistorChannelConfig,
    I2cThermistorInterfaceCapability,
    I2cWriteReg,
)
from gwsproto.property_format import SpaceheatName

from bus_talk import BusTalk, the_bus_node
from drivers import ads1115
from plant import Heard, Said, Send, ThermistorInput, ThermistorRead

THERMISTOR_T0 = 298.15  # i.e. 25 degrees
THERMISTOR_R0_KOHMS = 10


class ThermistorChannels(NamedTuple):
    """A reader's enabled channels. A thermistor is one wire read as two
    channels, its microvolts (electrical) and its temperature (device).
    Interior to the scada and never serialised."""

    device_configs: dict[SpaceheatName, I2cThermistorChannelConfig]
    electrical_configs: dict[SpaceheatName, I2cThermistorChannelConfig]
    electrical_cfg_by_device: dict[SpaceheatName, I2cThermistorChannelConfig]


def thermistor_channels(layout: HydronicLayout, node: ShNode) -> ThermistorChannels:
    component = node.component
    assert isinstance(component, I2cThermistorReaderComponent)
    device_configs: dict[SpaceheatName, I2cThermistorChannelConfig] = {}
    electrical_configs: dict[SpaceheatName, I2cThermistorChannelConfig] = {}
    # When either half of a thermistor is disabled neither is read.
    disabled_about: set[SpaceheatName] = set()

    for cfg in component.gt.ConfigList:
        if cfg.ChannelName not in layout.data_channels:
            raise ValueError(f"{node.name}: channel {cfg.ChannelName} not found in layout")
        ch = layout.data_channels[cfg.ChannelName]
        if layout.node_disabled(node.name) or layout.channel_disabled(ch.Name):
            disabled_about.add(ch.AboutNodeName)
            continue
        if ch.TelemetryName == TelemetryName.MicroVolts:
            electrical_configs[ch.Name] = cfg
        elif ch.TelemetryName == TelemetryName.CelsiusTimes100:
            device_configs[ch.Name] = cfg
        else:
            raise ValueError(
                f"{node.name}: unsupported TelemetryName {ch.TelemetryName} "
                f"for channel {ch.Name}"
            )

    device_configs = {
        name: cfg
        for name, cfg in device_configs.items()
        if layout.data_channels[name].AboutNodeName not in disabled_about
    }
    electrical_configs = {
        name: cfg
        for name, cfg in electrical_configs.items()
        if layout.data_channels[name].AboutNodeName not in disabled_about
    }

    electrical_by_about: dict[SpaceheatName, SpaceheatName] = {}
    for ch_name in electrical_configs:
        about = layout.data_channels[ch_name].AboutNodeName
        if about in electrical_by_about:
            raise ValueError(
                f"{node.name}: multiple electrical channels for AboutNodeName {about}"
            )
        electrical_by_about[about] = ch_name

    electrical_cfg_by_device: dict[SpaceheatName, I2cThermistorChannelConfig] = {}
    for device_name in device_configs:
        about = layout.data_channels[device_name].AboutNodeName
        if about not in electrical_by_about:
            raise ValueError(f"{node.name}: no electrical channel for AboutNodeName {about}")
        electrical_cfg_by_device[device_name] = electrical_configs[electrical_by_about[about]]

    return ThermistorChannels(device_configs, electrical_configs, electrical_cfg_by_device)


class ThermistorAdc(NamedTuple):
    """Where a reader's thermistors sit on its board. Interior to the scada
    and never serialised: no word carries a resolved ADC."""

    bus_node: ShNode
    capability: I2cThermistorInterfaceCapability
    data_rate_sps: int
    temp_calc_method: TempCalcMethod
    channels: ThermistorChannels


def resolve_thermistor_adc(layout: HydronicLayout, node: ShNode) -> ThermistorAdc:
    """AdcName resolved against the component's own board record, which
    carries the physical facts (bus, address, reference volts, series
    resistance). The layout's own validation guarantees the name is
    present."""
    component = node.component
    assert isinstance(component, I2cThermistorReaderComponent)
    record = component.board_component.device_type
    return ThermistorAdc(
        bus_node=the_bus_node(layout, node.name),
        capability=next(a for a in record.ThermistorAdcs if a.Name == component.gt.AdcName),
        data_rate_sps=component.gt.DataRateSps,
        temp_calc_method=component.gt.TempCalcMethod,
        channels=thermistor_channels(layout, node),
    )


def failed(summary: str, details: str) -> ThermistorRead:
    return ThermistorRead(None, None, (Said(summary, details, True),))


class Ads1115ThermistorInput(ThermistorInput):
    def __init__(self, at: ThermistorAdc) -> None:
        self.at = at
        self.bus = BusTalk(at.bus_node)

    def attach(self, send: Send) -> None:
        self.bus.attach(send)

    def hears(self, payload: Any) -> Heard:
        return Heard.Taken if self.bus.hears(payload) else Heard.NotMine

    async def read_volts(
        self, electrical_cfg: I2cThermistorChannelConfig
    ) -> tuple[float | None, str | None]:
        """One ADS1115 single-shot conversion through the bus actor:
        config write -> conversion wait -> config readback gate ->
        conversion read.

        The readback gate: the conversion register is only trusted after the
        config register reads back equal to the written word — OS set
        (conversion done) with MUX/PGA/DR unchanged. A garbled config write
        or a mid-sequence chip reset otherwise attributes the PREVIOUS
        conversion (previous channel's mux) to this channel with no error
        anywhere."""
        bus_name = self.at.bus_node.name
        address = self.at.capability.I2cAddress
        config = ads1115.config_word(electrical_cfg.AdcChannel, self.at.data_rate_sps)
        start = await self.bus.op(
            I2cWriteReg(
                Bus=bus_name,
                Address=I2cRegAddress(I2cAddress=address, RegisterIndex=ads1115.CONFIG_REG),
                NumBytes=2,
                Value=config,
                TriggerId=str(uuid.uuid4()),
            )
        )
        if start is None:
            return None, "bus op timeout starting conversion"
        if not start.Success:
            return None, start.Error
        readback = None
        for _attempt in range(2):
            await asyncio.sleep(ads1115.conversion_wait_s(self.at.data_rate_sps))
            conf = await self.bus.op(
                I2cReadReg(
                    Bus=bus_name,
                    Address=I2cRegAddress(I2cAddress=address, RegisterIndex=ads1115.CONFIG_REG),
                    NumBytes=2,
                    TriggerId=str(uuid.uuid4()),
                )
            )
            if conf is None:
                return None, "bus op timeout on config readback"
            if not conf.Success:
                return None, conf.Error
            readback = conf.Value
            if readback == config:
                break
        else:
            return None, (
                f"ADS config readback mismatch: wrote 0x{config:04x}, "
                f"read 0x{readback:04x}"
            )
        conv = await self.bus.op(
            I2cReadReg(
                Bus=bus_name,
                Address=I2cRegAddress(I2cAddress=address, RegisterIndex=ads1115.CONVERSION_REG),
                NumBytes=2,
                TriggerId=str(uuid.uuid4()),
            )
        )
        if conv is None:
            return None, "bus op timeout reading conversion"
        if not conv.Success:
            return None, conv.Error
        return ads1115.volts_from_raw(conv.Value), None

    def temp_beta(self, cfg: I2cThermistorChannelConfig, r_therm_kohms: float) -> float:
        if self.at.temp_calc_method != TempCalcMethod.SimpleBeta:
            raise ValueError(
                f"Using temp_beta when TempCalcMethod is {self.at.temp_calc_method}"
            )
        return (
            1 / ((1 / THERMISTOR_T0) + (math.log(r_therm_kohms / THERMISTOR_R0_KOHMS) / cfg.ThermistorBeta))
            - 273
        )

    async def read(self, temp_channel_name: SpaceheatName) -> ThermistorRead:
        device_cfg = self.at.channels.device_configs[temp_channel_name]
        electrical_cfg = self.at.channels.electrical_cfg_by_device[temp_channel_name]
        volts, error = await self.read_volts(electrical_cfg)
        if volts is None:
            return failed("i2c-thermistor-read-failed", f"{error}")

        r_fixed = self.at.capability.SeriesResistanceKOhms
        v_ref = self.at.capability.AdcReferenceVolts
        if volts <= 0.01:
            return failed(
                "i2c-thermistor-shorted", f"{volts:.6f} V indicates a shorted thermistor"
            )
        if volts >= v_ref:
            return failed(
                "i2c-thermistor-broken",
                f"{volts:.6f} V indicates a broken or missing thermistor",
            )
        try:
            microvolts = int(volts * 1_000_000)
            r_therm = r_fixed * volts / (v_ref - volts)
            temp_c = self.temp_beta(device_cfg, r_therm)
            if temp_c <= 0:
                return failed(
                    "i2c-thermistor-broken",
                    f"{volts:.6f} V implies {temp_c:.2f} C, indicating a broken or missing thermistor",
                )
            temp_c_x100 = int(temp_c * 100)
        except Exception as e:  # noqa: BLE001
            return failed("i2c-thermistor-invalid-reading", f"failed to convert reading ({e})")
        return ThermistorRead(microvolts, temp_c_x100, ())
