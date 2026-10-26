"""The dist pump monitor's zone-call read on both sim House0 pairs: it reads
each zone's derived heat-call channel, so it sees a call whichever raw source
(opto input or whitewire power) the layout derives it from."""

import time
from pathlib import Path

import pytest

from actors.derived_generator import DerivedGenerator
from actors.leaf_ally.house0.all_tanks import AllTanksLeafAlly
from actors.scada import Scada
from gwsproto.named_types import SingleReading
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.channel_names import (
    HydronicSpaceheatZoneChannelNames as HSZoneChannelNames,
)
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "house0-willow": ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json"),
    "house0-orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
}


@pytest.fixture(params=sorted(PAIRS))
def app(request: pytest.FixtureRequest) -> ScadaApp:
    layout, ops = PAIRS[request.param]
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


@pytest.fixture
def leaf_ally(app: ScadaApp) -> AllTanksLeafAlly:
    impl = app.get_communicator(CoreNodeNames.leaf_ally)._impl
    assert isinstance(impl, AllTanksLeafAlly)
    return impl


@pytest.fixture
def derived(app: ScadaApp) -> DerivedGenerator:
    """The derived generator with its send to the primary scada delivered
    in-process, so a derived reading lands in the shared scada data the way
    it does at runtime."""
    gen = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert gen is not None
    scada = app.get_communicator_as_type(CoreNodeNames.primary_scada, Scada)
    assert scada is not None

    def deliver(dst, payload, src=None):
        if dst.name == CoreNodeNames.primary_scada and isinstance(payload, SingleReading):
            scada.process_single_reading(gen.node, payload)

    gen._send_to = deliver
    return gen


def heat_call_names(actor: AllTanksLeafAlly) -> list[str]:
    return [HSZoneChannelNames(zone, i + 1).heat_call for i, zone in enumerate(actor.layout.zone_list)]


def test_heat_call_channels_are_in_the_layout(leaf_ally: AllTanksLeafAlly) -> None:
    for name in heat_call_names(leaf_ally):
        assert name in leaf_ally.layout.derived_channels
        assert leaf_ally.layout.derived_channels[name].Strategy == "heat-call"


def test_no_reading_means_no_zone_calling(leaf_ally: AllTanksLeafAlly) -> None:
    for name in heat_call_names(leaf_ally):
        leaf_ally.data.latest_channel_values.pop(name, None)
    assert leaf_ally.dist_pump_monitor._any_zones_calling() is False


def test_derived_heat_call_decides(leaf_ally: AllTanksLeafAlly) -> None:
    names = heat_call_names(leaf_ally)
    for name in names:
        leaf_ally.data.latest_channel_values[name] = 0
    assert leaf_ally.dist_pump_monitor._any_zones_calling() is False
    leaf_ally.data.latest_channel_values[names[0]] = 1
    assert leaf_ally.dist_pump_monitor._any_zones_calling() is True


def whitewire_reading(derived: DerivedGenerator, zone_idx: int, watts: int) -> SingleReading:
    zone = derived.layout.zone_list[zone_idx]
    return SingleReading(
        ChannelName=HSZoneChannelNames(zone, zone_idx + 1).whitewire_pwr,
        Value=watts,
        ScadaReadTimeUnixMs=int(time.time() * 1000),
    )


def test_whitewire_power_through_the_derived_generator(
    leaf_ally: AllTanksLeafAlly, derived: DerivedGenerator
) -> None:
    """The sim House0 pairs derive heat-call from whitewire power above the
    channel's Threshold (10 W): low power is no call, high power is a call."""
    names = heat_call_names(leaf_ally)
    for name in names:
        leaf_ally.data.latest_channel_values.pop(name, None)
    assert leaf_ally.dist_pump_monitor._any_zones_calling() is False  # no signal yet

    power_meter = derived.layout.node(derived.layout.data_channels[
        HSZoneChannelNames(derived.layout.zone_list[0], 1).whitewire_pwr
    ].CapturedByNodeName)
    derived.handle_input_reading(power_meter, whitewire_reading(derived, 0, 3))
    assert leaf_ally.data.latest_channel_values[names[0]] == 0
    assert leaf_ally.dist_pump_monitor._any_zones_calling() is False

    derived.handle_input_reading(power_meter, whitewire_reading(derived, 0, 40))
    assert leaf_ally.data.latest_channel_values[names[0]] == 1
    assert leaf_ally.dist_pump_monitor._any_zones_calling() is True

    derived.handle_input_reading(power_meter, whitewire_reading(derived, 0, 0))
    assert leaf_ally.data.latest_channel_values[names[0]] == 0
    assert leaf_ally.dist_pump_monitor._any_zones_calling() is False
