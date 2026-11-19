"""A plant that stands still, inside the scada.

A simulated layout run with no terminal asset still needs a plant to show
its sensors. The standing plant link is the plant link with that plant
inside it: every channel a simulated device senses holds one value for
ever, and no relay moves any of them. It is there to run the scada's own
code on a laptop. A plant whose values answer the relays is a terminal
asset, behind the broker link.

The one thing a relay changes is pico power: a simulated pico goes quiet
on its layout's schedule and comes back when the vdc relay cycles, so the
pico cycler has something to recover.
"""

import asyncio
from typing import Callable, Mapping, Optional, Sequence

from gwsproto.data_classes.components import (
    ElectricMeterComponent,
    GpioRelayComponent,
    GpioSensorComponent,
    I2cRelayComponent,
    I2cThermistorReaderComponent,
    SimPicoBtuMeterComponent,
    SimPicoTankModuleComponent,
)
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import (
    ActorClass,
    ChangeRelayPin,
    RelayClosedOrOpen,
    SimDeviceType,
    TelemetryName,
)
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames

from actors.api_tank_module import microvolts_at_c
from drivers import ads1115
from drivers.sim_i2c import SIM_THERMISTOR_RAW
from plant import PlantReadings
from plant_link import PlantLink
from thermistor_inputs import resolve_thermistor_adc, thermistor_reading

TICK_S = 1
SIM_SENSOR_FLUX_S = 5

# Plausible values in each telemetry's own scaling. A telemetry not listed
# stands at 0, which is idle for a power or a flow.
SIM_SENSOR_VALUE_BY_TELEMETRY: dict[TelemetryName, int] = {
    TelemetryName.WaterTempCTimes1000: 50_000,
    TelemetryName.WaterTempFTimes1000: 122_000,
    TelemetryName.AirTempCTimes1000: 21_000,
    TelemetryName.AirTempFTimes1000: 70_000,
    TelemetryName.CelsiusTimes100: 5_000,
    TelemetryName.HzTimes100: 6_000,
    TelemetryName.GpmTimes100: 400,
    TelemetryName.MicroHz: 2_000_000,
}
# A tank at rest, stratified: depth1 is the top.
TANK_AT_REST_C: dict[int, float] = {1: 55.0, 2: 50.0, 3: 45.0}
# A loop with standing flow and no lift, and no CT voltage.
LOOP_GPM_X100 = 400
LOOP_C = 50.0
CT_VOLTS_X100 = 0
PIN_AT_REST = 1


def enabled(layout: HydronicLayout, values: Mapping[str, int]) -> dict[str, int]:
    return {
        name: value
        for name, value in values.items()
        if name in layout.data_channels and not layout.channel_disabled(name)
    }


def captured_by(layout: HydronicLayout, node: ShNode) -> list[str]:
    return [ch.Name for ch in layout.data_channels.values() if ch.CapturedByNodeName == node.name]


def sim_sensor_values(layout: HydronicLayout) -> dict[str, int]:
    return enabled(
        layout,
        {
            name: SIM_SENSOR_VALUE_BY_TELEMETRY.get(layout.data_channels[name].TelemetryName, 0)
            for node in layout.nodes.values()
            if node.actor_class == ActorClass.SimSensorActor
            and not layout.node_disabled(node.name)
            for name in captured_by(layout, node)
        },
    )


def meter_values(layout: HydronicLayout) -> dict[str, int]:
    return {
        config.ChannelName: 0
        for node in layout.nodes.values()
        if node.actor_class == ActorClass.PowerMeter
        and isinstance(node.component, ElectricMeterComponent)
        and node.component.device_type.DeviceType == SimDeviceType.SimPowerMeter
        for config in node.component.gt.ConfigList
    }


def pin_values(layout: HydronicLayout) -> dict[str, int]:
    return {
        name: PIN_AT_REST
        for node in layout.nodes.values()
        if node.actor_class == ActorClass.GpioSensor
        and isinstance(node.component, GpioSensorComponent)
        and node.component.board_component.simulated
        for name in captured_by(layout, node)
    }


def thermistor_values(layout: HydronicLayout) -> dict[str, int]:
    """Each board thermistor as its reader makes of the voltage a simulated
    ADC holds, so a simulated reader reports what it would read off the
    bus's own fake chip."""
    volts = ads1115.volts_from_raw(SIM_THERMISTOR_RAW)
    values: dict[str, int] = {}
    for node in layout.nodes.values():
        component = node.component
        if not (
            node.actor_class == ActorClass.I2cThermistorReader
            and isinstance(component, I2cThermistorReaderComponent)
            and component.board_component.simulated
        ):
            continue
        adc = resolve_thermistor_adc(layout, node)
        for temp_channel, electrical_cfg in adc.channels.electrical_cfg_by_device.items():
            read = thermistor_reading(adc, temp_channel, volts)
            if read.temp_c_x100 is None or read.microvolts is None:
                raise ValueError(
                    f"{temp_channel}: the standing {volts:.4f} V is no temperature "
                    f"({'; '.join(said.details for said in read.said)})"
                )
            values[temp_channel] = read.temp_c_x100
            values[electrical_cfg.ChannelName] = read.microvolts
    return values


def tank_values(layout: HydronicLayout, node: ShNode) -> dict[str, int]:
    component = node.component
    assert isinstance(component, SimPicoTankModuleComponent)
    values: dict[str, int] = {}
    for depth, celsius in TANK_AT_REST_C.items():
        device_channel = f"{node.name}-depth{depth}-device"
        if device_channel in layout.data_channels:
            values[device_channel] = layout.channel_registry.temperature_from_c(
                device_channel, celsius
            ).raw
        values[f"{node.name}-depth{depth}-micro-v"] = microvolts_at_c(
            celsius, component.gt.ThermistorBeta
        )
    return enabled(layout, values)


def loop_values(layout: HydronicLayout, node: ShNode) -> dict[str, int]:
    component = node.component
    assert isinstance(component, SimPicoBtuMeterComponent)
    meter = component.gt
    values: dict[str, int] = {meter.FlowChannelName: LOOP_GPM_X100}
    for pipe_channel in (meter.HotChannelName, meter.ColdChannelName):
        if pipe_channel in layout.data_channels:
            values[pipe_channel] = layout.channel_registry.temperature_from_c(
                pipe_channel, LOOP_C
            ).raw
    if meter.CtChannelName:
        values[meter.CtChannelName] = CT_VOLTS_X100
    return enabled(layout, values)


def vdc_relay_states(layout: HydronicLayout) -> dict[ChangeRelayPin, RelayClosedOrOpen]:
    """Whether the relay on the picos' supply is closed or open at each of
    its positions. Empty for a layout with no such relay."""
    node = layout.nodes.get(HydronicSpaceheatNodeNames.vdc_relay)
    if node is None or not isinstance(node.component, (I2cRelayComponent, GpioRelayComponent)):
        return {}
    config = next((c for c in node.component.gt.ConfigList if c.ActorName == node.name), None)
    if config is None:
        return {}
    return {
        ChangeRelayPin.Energize: RelayClosedOrOpen(config.EnergizedState),
        ChangeRelayPin.DeEnergize: RelayClosedOrOpen(config.DeEnergizedState),
    }


class StandingPico:
    """When one simulated pico posts, and whether it has power.

    It posts its channels once a capture period. Alive for SimLifeS since
    its boot, it dies and stays quiet. Power follows the vdc relay: an open
    kills it at once, and the close that follows an open boots it
    SimRebootS later, the way a board rejoins wifi after a power cycle, so
    a pico-cycler cycle revives it. SimLifeS absent is a pico that never
    dies on its own; SimRebootS absent is one that stays dead.

    The death is a schedule and not a failure model, and a reboot always
    succeeds. Every method takes the current time, so a test drives it
    with no clock."""

    def __init__(
        self,
        values: Mapping[str, int],
        capture_period_s: int,
        life_s: Optional[int],
        reboot_s: Optional[int],
        booted_at: float,
    ) -> None:
        self.values = values
        self.capture_period_s = capture_period_s
        self.life_s = life_s
        self.reboot_s = reboot_s
        self.alive = True
        self.booted_at = booted_at
        self.last_post: Optional[float] = None
        self.relay_open_seen = False
        self.reboot_at: Optional[float] = None

    def relay_state(self, state: RelayClosedOrOpen, now: float) -> None:
        if state == RelayClosedOrOpen.RelayOpen:
            self.alive = False
            self.reboot_at = None
            self.relay_open_seen = True
        elif self.relay_open_seen:
            self.relay_open_seen = False
            if self.reboot_s is not None:
                self.reboot_at = now + self.reboot_s

    def tick(self, now: float) -> Mapping[str, int]:
        """Advance to now: the channels to post, none unless a post is due."""
        if not self.alive:
            if self.reboot_at is None or now < self.reboot_at:
                return {}
            self.alive = True
            self.booted_at = now
            self.last_post = None
            self.reboot_at = None
        if self.life_s is not None and now - self.booted_at >= self.life_s:
            self.alive = False
            return {}
        if self.last_post is not None and now - self.last_post < self.capture_period_s:
            return {}
        self.last_post = now
        return self.values


def standing_picos(layout: HydronicLayout, now: float) -> list[StandingPico]:
    picos: list[StandingPico] = []
    for node in layout.nodes.values():
        component = node.component
        if layout.node_disabled(node.name):
            continue
        if isinstance(component, SimPicoTankModuleComponent):
            values = tank_values(layout, node)
            period_channel = f"{node.name}-depth1-device"
        elif isinstance(component, SimPicoBtuMeterComponent):
            values = loop_values(layout, node)
            period_channel = component.gt.FlowChannelName
        else:
            continue
        picos.append(
            StandingPico(
                values,
                capture_period_s=layout.capture_tuning_by_channel[period_channel].CapturePeriodS,
                life_s=component.gt.SimLifeS,
                reboot_s=component.gt.SimRebootS,
                booted_at=now,
            )
        )
    return picos


class StandingPlantLink(PlantLink):
    """The plant link whose plant is a task of the scada's own, showing a
    flux each second. Nothing crosses a broker."""

    def __init__(
        self,
        layout: HydronicLayout,
        *,
        silent_after_s: float,
        monotonic: Callable[[], float],
        wall: Callable[[], float],
    ) -> None:
        super().__init__(silent_after_s=silent_after_s, monotonic=monotonic)
        self.wall = wall
        self.read_when_asked = {
            **meter_values(layout),
            **pin_values(layout),
            **thermistor_values(layout),
        }
        # This plant is there before the scada starts, so a device asked
        # ahead of the first tick reads what stands. A meter that read
        # nothing at boot would leave the heat pump's state unknown for its
        # first second, and HpBoss runs the secondary pump while it is.
        self.latest = dict(self.read_when_asked)
        self.sim_sensors = sim_sensor_values(layout)
        self.sim_sensors_shown_at: Optional[float] = None
        self.picos = standing_picos(layout, wall())
        self.vdc_states = vdc_relay_states(layout)
        self.stop_requested = False

    def start(self) -> Sequence[asyncio.Task[None]]:
        return [asyncio.create_task(self.run(), name="standing plant")]

    def stop(self) -> None:
        self.stop_requested = True

    async def run(self) -> None:
        while not self.stop_requested:
            self.tick(self.wall())
            await asyncio.sleep(TICK_S)

    def showing(self, now: float) -> dict[str, int]:
        """What the plant shows at now. A flux is all a plant shows, so a
        channel read when asked is there every time. A channel handed to its
        sensor as it arrives is there only when that sensor is due a
        reading."""
        values = dict(self.read_when_asked)
        if (
            self.sim_sensors_shown_at is None
            or now - self.sim_sensors_shown_at >= SIM_SENSOR_FLUX_S
        ):
            self.sim_sensors_shown_at = now
            values.update(self.sim_sensors)
        for pico in self.picos:
            values.update(pico.tick(now))
        return values

    def tick(self, now: float) -> None:
        values = self.showing(now)
        self.take(
            PlantReadings(
                channel_names=tuple(values),
                values=tuple(values.values()),
                read_time_ms=int(now * 1000),
            )
        )

    def actuate(self, relay_name: str, action: ChangeRelayPin) -> None:
        if relay_name != HydronicSpaceheatNodeNames.vdc_relay or action not in self.vdc_states:
            return
        now = self.wall()
        for pico in self.picos:
            pico.relay_state(self.vdc_states[action], now)
