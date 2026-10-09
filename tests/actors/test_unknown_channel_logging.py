"""The scada can say which channels it holds no usable value for: those
with no value at all, and those whose value has aged past the flatline
bound."""

import time
from pathlib import Path

from actors.scada_data import UnknownChannels
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"


def willow_app() -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.house0.willow.layout.json"
    settings.paths.operational_params = CONFIG / "gw.house0.willow.operational.params.json"
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


def test_unknown_channels_separates_no_value_from_stale() -> None:
    data = willow_app().scada.data
    now_ms = int(time.time() * 1000)
    for ch in data.my_channels:
        data.latest_channel_values[ch.Name] = 1
        data.latest_channel_unix_ms[ch.Name] = now_ms
    assert data.unknown_channels() == UnknownChannels(no_value=[], stale=[])

    data.flush_channel_from_latest(HCN.hp_odu_pwr)
    period_ms = 1000 * data.capture_seconds(data.layout.data_channels[HCN.hp_idu_pwr])
    data.latest_channel_unix_ms[HCN.hp_idu_pwr] = now_ms - 3 * period_ms
    assert data.unknown_channels() == UnknownChannels(
        no_value=[HCN.hp_odu_pwr], stale=[HCN.hp_idu_pwr]
    )


def nolan_app() -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.nolan.layout.json"
    settings.paths.operational_params = CONFIG / "gw.nolan.operational.params.json"
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


def test_a_derived_channel_ages_on_its_own_emit_period() -> None:
    """A periodic derived channel is fresh for its emit period, not for a
    bound shared by every derived channel; an on-trigger one ages with the
    slowest input it is derived from."""
    data = nolan_app().scada.data
    now_ms = int(time.time() * 1000)
    for ch in data.my_channels:
        data.latest_channel_values[ch.Name] = 1
        data.latest_channel_unix_ms[ch.Name] = now_ms
    heat_call = data.layout.derived_channels["zone1-bedrooms-heat-call"]
    usable = data.layout.derived_channels["usable-energy"]
    depth1 = data.layout.derived_channels["buffer-depth1"]
    assert heat_call.EmitPeriodS == 300
    assert usable.EmitPeriodS == 60
    assert depth1.EmitPeriodS is None
    device_s = data.capture_seconds(data.layout.data_channels["buffer-depth1-device"])
    assert data.capture_seconds(heat_call) == 300
    assert data.capture_seconds(usable) == 60
    assert data.capture_seconds(depth1) == device_s

    age_ms = 200_000
    for name in (heat_call.Name, usable.Name, depth1.Name):
        data.latest_channel_unix_ms[name] = now_ms - age_ms
    unknown = data.unknown_channels()
    assert heat_call.Name not in unknown.stale
    assert usable.Name in unknown.stale
    assert (depth1.Name in unknown.stale) == (age_ms > 1000 * device_s * 2.1)
