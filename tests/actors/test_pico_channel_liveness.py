"""A pico that keeps posting and drops one channel: the actor tells the
scada that channel has flatlined after 2.5 of its capture periods, and
does not call the pico missing. The BTU meter is the Nolan sim's
store-btu; the tank module is the willow sim's tank1. Each actor's clock
is driven by the test, its sim source ticked once a second and its
liveness checked every ten, as `sim_pico_main` and `main` do."""

import time
from pathlib import Path
from typing import Union

import pytest

import actors.api_btu_meter as api_btu_meter
import actors.api_tank_module as api_tank_module
from actors.api_btu_meter import ApiBtuMeter
from actors.api_tank_module import ApiTankModule
from actors.pico_liveness import PicoLiveness
from gwsproto.named_types import ChannelFlatlined, PicoMissing
from gwsproto.names.core.node_names import CoreNodeNames
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PicoActor = Union[ApiBtuMeter, ApiTankModule]


class Clock:
    """Stands in for the `time` module in a pico actor's module."""

    def __init__(self, now: float) -> None:
        self.now = now

    def time(self) -> float:
        return self.now


class Rig:
    """One pico actor with its sends recorded, those for the scada also
    delivered to it."""

    def __init__(self, app: ScadaApp, actor: PicoActor, clock: Clock, omit: str, channel: str) -> None:
        self.actor = actor
        self.clock = clock
        self.omit = omit
        """The name the sim source drops from its reading."""
        self.channel = channel
        """The data channel that goes quiet when it does."""
        self.data = app.scada.data
        self.sent: list = []
        scada = app.scada

        def send_to(dst, payload, src=None) -> None:
            self.sent.append(payload)
            if dst.name == CoreNodeNames.primary_scada:
                scada.process_scada_message(actor.node, payload)

        actor._send_to = send_to

    def run(self, seconds: int) -> None:
        source = self.actor.sim_pico
        assert source is not None
        for second in range(seconds):
            self.clock.now += 1
            reading = source.tick(self.clock.now)
            if reading is not None:
                if isinstance(self.actor, ApiBtuMeter):
                    self.actor._process_multichannel_snapshot(reading)
                else:
                    self.actor._process_microvolts(reading)
            if second % 10 == 0:
                self.actor.check_liveness()

    def flatlined(self) -> list[str]:
        return [p.Channel.Name for p in self.sent if isinstance(p, ChannelFlatlined)]

    def missing(self) -> list[PicoMissing]:
        return [p for p in self.sent if isinstance(p, PicoMissing)]

    def quiet_seconds(self) -> int:
        period = self.actor.layout.capture_tuning_by_channel[self.channel].CapturePeriodS
        return int(period * PicoLiveness.MISSING_MULTIPLE)


def make_app(layout: str, ops: str) -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


@pytest.fixture(params=["btu", "tank"])
def rig(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Rig:
    clock = Clock(time.time())
    if request.param == "btu":
        app = make_app("gw.nolan.layout.json", "gw.nolan.operational.params.json")
        actor = app.get_communicator_as_type("store-btu", ApiBtuMeter)
        assert actor is not None
        monkeypatch.setattr(api_btu_meter, "time", clock)
        return Rig(app, actor, clock, omit="store-cold-pipe", channel="store-cold-pipe")
    app = make_app("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json")
    actor = app.get_communicator_as_type("tank1", ApiTankModule)
    assert actor is not None
    monkeypatch.setattr(api_tank_module, "time", clock)
    return Rig(app, actor, clock, omit="tank1-depth2", channel="tank1-depth2-device")


def test_one_quiet_channel_is_flatlined_and_the_pico_is_not_missing(rig: Rig) -> None:
    rig.actor.sim_pico.life_s = None
    rig.run(5)
    assert rig.data.latest_channel_values[rig.channel] is not None
    rig.actor.sim_pico.omitted_names = {rig.omit}
    rig.run(rig.quiet_seconds() + 30)
    quiet = [name for name in rig.flatlined() if name.startswith(rig.omit)]
    assert rig.channel in quiet
    assert len(quiet) == len(set(quiet))
    assert rig.flatlined() == quiet
    assert rig.missing() == []
    assert rig.data.latest_channel_values[rig.channel] is None


def test_a_channel_that_misses_one_post_is_not_flatlined(rig: Rig) -> None:
    rig.actor.sim_pico.life_s = None
    rig.run(5)
    rig.actor.sim_pico.omitted_names = {rig.omit}
    rig.run(rig.actor.sim_pico.capture_period_s)
    rig.actor.sim_pico.omitted_names = set()
    rig.run(rig.quiet_seconds())
    assert rig.flatlined() == []
    assert rig.data.latest_channel_values[rig.channel] is not None


def test_a_dead_pico_is_reported_once_and_not_channel_by_channel(rig: Rig) -> None:
    life_s = 20
    rig.actor.sim_pico.life_s = life_s
    rig.actor.sim_pico.booted_at = rig.clock.now
    rig.run(life_s + int(rig.actor.flatline_seconds()) + 40)
    assert len(rig.missing()) == 1
    flatlined = rig.flatlined()
    assert flatlined
    assert len(flatlined) == len(set(flatlined))
