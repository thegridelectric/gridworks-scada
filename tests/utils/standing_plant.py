import math
import time
from typing import Iterable, Mapping

from gwsproto.data_classes.components import (
    ElectricMeterComponent,
    SimPicoBtuMeterComponent,
    SimPicoTankModuleComponent,
)
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.enums import ActorClass

from actors.api_tank_module import microvolts_at_c
from plant_link import InProcessPlantLink
from scada_app import ScadaApp

# A tank at rest, stratified: depth1 is the top.
TANK_AT_REST_C: dict[int, float] = {1: 55.0, 2: 50.0, 3: 45.0}
# A loop with standing flow and no lift, and no CT voltage.
LOOP_GPM_X100 = 400
LOOP_C = 50.0
CT_VOLTS_X100 = 0


def tanks_at_rest(layout: HydronicLayout) -> dict[str, int]:
    values: dict[str, int] = {}
    for node in layout.nodes.values():
        if not isinstance(node.component, SimPicoTankModuleComponent):
            continue
        for depth, celsius in TANK_AT_REST_C.items():
            device_channel = f"{node.name}-depth{depth}-device"
            values[device_channel] = layout.channel_registry.temperature_from_c(
                device_channel, celsius
            ).raw
            values[f"{node.name}-depth{depth}-micro-v"] = microvolts_at_c(
                celsius, node.component.gt.ThermistorBeta
            )
    return values


def loops_standing(layout: HydronicLayout) -> dict[str, int]:
    values: dict[str, int] = {}
    for node in layout.nodes.values():
        if not isinstance(node.component, SimPicoBtuMeterComponent):
            continue
        meter = node.component.gt
        values[meter.FlowChannelName] = LOOP_GPM_X100
        for pipe_channel in (meter.HotChannelName, meter.ColdChannelName):
            values[pipe_channel] = layout.channel_registry.temperature_from_c(
                pipe_channel, LOOP_C
            ).raw
        if meter.CtChannelName:
            values[meter.CtChannelName] = CT_VOLTS_X100
    return values


class StandingPlant:
    """The plant a test plays for a scada on a simulated layout. It is
    always there, and what it shows stands until the test changes it: each
    change reaches the scada as one whole flux, as a plant's does. It
    starts with every metered channel at 0 W, every tank at rest and every
    BTU-metered loop with standing flow and no lift."""

    def __init__(self, app: ScadaApp) -> None:
        link = app.plant_link
        assert isinstance(link, InProcessPlantLink)
        self.link = link
        link.silent_after_s = math.inf
        layout = app.hardware_layout
        self.metered_channel_names = [
            config.ChannelName
            for node in layout.nodes.values()
            if node.actor_class == ActorClass.PowerMeter
            and isinstance(node.component, ElectricMeterComponent)
            for config in node.component.gt.ConfigList
        ]
        self.hidden: set[str] = set()
        self.values: dict[str, int] = {
            **{name: 0 for name in self.metered_channel_names},
            **{
                name: value
                for name, value in {**tanks_at_rest(layout), **loops_standing(layout)}.items()
                if name in layout.data_channels and not layout.channel_disabled(name)
            },
        }
        self.scada_runs = False
        self.flux()

    def flux(self) -> None:
        # A channel handed to its actor as the flux arrives makes that actor
        # send, which it cannot do before its scada runs: until then the
        # plant shows only what is read when asked.
        self.link.show(
            {
                name: value
                for name, value in self.values.items()
                if name not in self.hidden
                and (self.scada_runs or name in self.link.polled_channels)
            },
            int(time.time() * 1000),
        )

    def scada_started(self) -> None:
        self.scada_runs = True
        self.flux()

    def show(self, values: Mapping[str, int]) -> None:
        self.values.update(values)
        self.flux()

    def hide(self, channel_names: Iterable[str]) -> None:
        """The plant shows every channel but these."""
        self.hidden = set(channel_names)
        self.flux()

    def meter_reads(self, watts: int) -> None:
        self.show({name: watts for name in self.metered_channel_names})
