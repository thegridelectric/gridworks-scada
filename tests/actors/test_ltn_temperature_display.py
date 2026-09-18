"""The LTN's snapshot log line and the dashboard's unbound-readings table
show a temperature channel in degrees, whatever encoding the channel
declares, and leave every other channel raw."""

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from actors.ltn.dashboard.channels.read_mixin import UnboundReading
from actors.ltn.dashboard.display.odds_and_ends import OddsAndEnds
from actors.ltn.ltn import Ltn
from gwsproto.enums import TelemetryName, Unit
from gwsproto.named_types import SingleReading, SnapshotSpaceheat
from sema_to_dc import load_layout

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "willow": ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json"),
    "orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
}
T_MS = 1_700_000_000_000


@pytest.mark.parametrize("pair_name", sorted(PAIRS))
@pytest.mark.parametrize(("c_to_f", "shown"), [(True, "122.00 F"), (False, "50.00 C")])
def test_snapshot_str_shows_degrees_for_temperatures_and_raw_for_the_rest(
    pair_name: str, c_to_f: bool, shown: str
) -> None:
    layout_name, ops_name = PAIRS[pair_name]
    layout = load_layout(CONFIG / layout_name, CONFIG / ops_name)
    registry = layout.channel_registry
    temp_channel = next(
        name
        for name, ch in layout.data_channels.items()
        if ch.TelemetryName == TelemetryName.CelsiusTimes100
    )
    other_channel = next(
        name
        for name, ch in layout.data_channels.items()
        if ch.TelemetryName == TelemetryName.PowerW
    )
    snapshot = SnapshotSpaceheat(
        FromGNodeAlias=layout.scada_g_node_alias,
        FromGNodeInstanceId=str(uuid.uuid4()),
        SnapshotTimeUnixMs=T_MS,
        LatestReadingList=[
            SingleReading(
                ChannelName=temp_channel,
                Value=registry.temperature_from_c(temp_channel, 50.0).raw,
                ScadaReadTimeUnixMs=T_MS,
            ),
            SingleReading(ChannelName=other_channel, Value=4321, ScadaReadTimeUnixMs=T_MS),
        ],
        LatestStateList=[],
    )
    ltn = SimpleNamespace(layout=layout, settings=SimpleNamespace(c_to_f=c_to_f))

    lines = Ltn.snapshot_str(ltn, snapshot).splitlines()  # type: ignore[arg-type]

    assert any(line.endswith(shown) for line in lines)
    assert any("4321" in line for line in lines)


def unbound(unit: TelemetryName | Unit | None, value: int) -> UnboundReading:
    return UnboundReading(
        ChannelName="some-channel", Value=value, ScadaReadTimeUnixMs=T_MS, Unit=unit
    )


@pytest.mark.parametrize(
    ("unit", "raw"),
    [
        (TelemetryName.CelsiusTimes100, 5000),
        (TelemetryName.WaterTempCTimes1000, 50000),
        (TelemetryName.AirTempFTimes1000, 122000),
        (Unit.FahrenheitX100, 12200),
    ],
)
def test_odds_and_ends_shows_a_temperature_in_f_in_any_encoding(
    unit: TelemetryName | Unit, raw: int
) -> None:
    display = OddsAndEnds(SimpleNamespace(last_unbound_readings=[]))  # type: ignore[arg-type]
    assert display._format_reading(unbound(unit, raw)) == ("122.00", "°F")


@pytest.mark.parametrize("unit", [TelemetryName.PowerW, None])
def test_odds_and_ends_shows_other_readings_raw(unit: TelemetryName | None) -> None:
    display = OddsAndEnds(SimpleNamespace(last_unbound_readings=[]))  # type: ignore[arg-type]
    value_str, _ = display._format_reading(unbound(unit, 4321))
    assert value_str == "4321"
