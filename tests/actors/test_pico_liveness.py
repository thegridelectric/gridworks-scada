"""One liveness rule for every pico-fed actor: missing after 2.5 expected
post periods of silence, the first report at the crossing, one more per
minute while the silence lasts, and a post resets it. The tank module
half checks the actor is wired to it on the sim fixtures."""

from pathlib import Path

import pytest

from actors.api_tank_module import ApiTankModule
from tests.actors.test_sim_pico import impl
from actors.pico_liveness import PicoLiveness
from gwsproto.named_types import ChannelFlatlined, PicoMissing
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
    "house0-sim": ("gw.house0.sim.layout.json", "gw.house0.sim.operational.params.json"),
}
PERIOD = 60


@pytest.fixture(params=sorted(PAIRS))
def app(request: pytest.FixtureRequest) -> ScadaApp:
    layout, ops = PAIRS[request.param]
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


def test_missing_after_two_and_a_half_periods() -> None:
    live = PicoLiveness(expected_post_s=PERIOD, now=0.0)
    assert live.flatline_seconds == 150
    assert not live.missing(60.0)
    assert not live.missing(150.0)
    assert live.missing(150.1)


def test_first_report_at_the_crossing_then_one_a_minute() -> None:
    live = PicoLiveness(expected_post_s=PERIOD, now=0.0)
    assert not live.report_due(100.0)
    assert live.report_due(151.0)
    assert not live.report_due(161.0)
    assert not live.report_due(210.0)
    assert live.report_due(211.0)
    assert not live.report_due(220.0)


def test_a_post_resets_the_report_clock() -> None:
    live = PicoLiveness(expected_post_s=PERIOD, now=0.0)
    assert live.report_due(151.0)
    live.heard(160.0)
    assert not live.missing(300.0)
    assert not live.report_due(300.0)
    assert live.report_due(311.0)


def test_a_zero_period_is_refused() -> None:
    with pytest.raises(ValueError):
        PicoLiveness(expected_post_s=0)


def tank_actors(app: ScadaApp) -> list[ApiTankModule]:
    return [
        impl(app.get_communicator(name))
        for name in app.get_communicator_names()
        if isinstance(impl(app.get_communicator(name)), ApiTankModule)
    ]


def test_tank_module_reports_through_the_shared_rule(app: ScadaApp) -> None:
    actors = tank_actors(app)
    assert actors, "no ApiTankModule actors on this layout"
    for a in actors:
        period = a.layout.capture_tuning_by_channel[f"{a.name}-depth1-device"].CapturePeriodS
        assert a.liveness.expected_post_s == period
        assert a.flatline_seconds() == period * PicoLiveness.MISSING_MULTIPLE
        sent: list = []
        a._send_to = lambda dst, payload, src=None, sent=sent: sent.append((dst.name, payload))
        a.report_missing()
        missing = [p for _, p in sent if isinstance(p, PicoMissing)]
        assert len(missing) == 1
        assert missing[0].ActorName == a.name
        assert missing[0].PicoHwUid == a.pico_uid
        flatlined = [p.Channel.Name for _, p in sent if isinstance(p, ChannelFlatlined)]
        assert flatlined == a.flatlined_channel_names()
