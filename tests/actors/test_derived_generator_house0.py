"""derived-generator on the sim House0 fixture: one pass of its main loop
after the first heating forecast, the pass that computes usable energy from
the tank temperatures. Guards the partition residue where the actor lost its
temperature read a minute into every boot and its watchdog stopped the
scada."""

import time
import uuid
from pathlib import Path

import pytest

from actors.derived_generator import DerivedGenerator
from gwsproto.data_classes.house_0_names import H0CN
from gwsproto.named_types import HeatingForecast
from gwsproto.names.core.node_names import CoreNodeNames
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"


@pytest.fixture
def app() -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.house0.orange.layout.json"
    settings.paths.operational_params = CONFIG / "gw.house0.orange.operational.params.json"
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


def a_day_of_forecast(actor: DerivedGenerator) -> HeatingForecast:
    """Hourly for 48 h from the next hour: a mild load, a required supply
    temperature below hot tanks, so extraction is possible."""
    top = int(time.time()) // 3600 * 3600 + 3600
    times = [top + 3600 * i for i in range(48)]
    return HeatingForecast(
        FromGNodeAlias=actor.layout.scada_g_node_alias,
        Time=times,
        AvgPowerKw=[3.0] * 48,
        RswtF=[120.0] * 48,
        RswtDeltaTF=[20.0] * 48,
        WeatherUid=str(uuid.uuid4()),
    )


def test_main_loop_pass_survives_the_first_forecast(app: ScadaApp) -> None:
    actor = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert actor is not None
    data = actor.data
    data.heating_forecast = a_day_of_forecast(actor)
    data.buffer_temps_available = True
    for tank in actor.h0cn.tank.values():
        for ch in (tank.depth1, tank.depth2, tank.depth3):
            data.latest_temperatures_f[ch] = 150.0
    for ch in (H0CN.buffer.depth1, H0CN.buffer.depth2, H0CN.buffer.depth3):
        data.latest_temperatures_f[ch] = 150.0

    usable_wh = actor.compute_usable_energy_wh()
    assert isinstance(usable_wh, int) and usable_wh > 0

    sent: list = []
    actor._send = lambda message: sent.append(message)
    actor._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    for dc in actor.system_models:
        actor.handle_system_model(dc)
    assert sent, "the pass emits its derived readings"
