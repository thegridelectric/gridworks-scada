"""A pico that keeps posting and drops one channel: the actor tells the
scada that channel has flatlined after 2.5 of its capture periods, and
does not call the pico missing. The BTU meter is the Nolan sim's
primary-btu; the tank module is the willow sim's tank1. Each actor's clock
is driven by the test, which plays the plant: it shows the actor's
channels once a capture period, and the actor's liveness is checked every
ten seconds, as its `main` does."""

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
from plant_link import InProcessPlantLink, PlantLinkKind
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
    delivered to it, and the plant that shows its channels."""

    def __init__(self, app: ScadaApp, actor: PicoActor, clock: Clock, omit: str, channel: str) -> None:
        self.actor = actor
        self.clock = clock
        self.omit = omit
        """The prefix of the channel names the plant can leave out."""
        self.channel = channel
        """The data channel that goes quiet when it does."""
        self.data = app.scada.data
        self.sent: list = []
        assert isinstance(app.plant_link, InProcessPlantLink)
        self.link = app.plant_link
        self.shown = {
            ch.Name: 4000
            for ch in actor.layout.data_channels.values()
            if ch.CapturedByNodeName == actor.name and not actor.layout.channel_disabled(ch.Name)
        }
        self.period_s = actor.layout.capture_tuning_by_channel[channel].CapturePeriodS
        self.omitting = False
        self.plant_shows = True
        self.ran_s = 0
        scada = app.scada

        def send_to(dst, payload, src=None) -> None:
            self.sent.append(payload)
            if dst.name == CoreNodeNames.primary_scada:
                scada.process_scada_message(actor.node, payload)

        actor._send_to = send_to

    def run(self, seconds: int) -> None:
        for _ in range(seconds):
            self.clock.now += 1
            if self.plant_shows and self.ran_s % self.period_s == 0:
                self.link.show(
                    {
                        name: value
                        for name, value in self.shown.items()
                        if not (self.omitting and name.startswith(self.omit))
                    },
                    int(self.clock.now * 1000),
                )
            if self.ran_s % 10 == 0:
                self.actor.check_liveness()
            self.ran_s += 1

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
    settings.plant_link = PlantLinkKind.InProcess
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


@pytest.fixture(params=["btu", "tank"])
def rig(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Rig:
    clock = Clock(time.time())
    if request.param == "btu":
        app = make_app("gw.nolan.layout.json", "gw.nolan.operational.params.json")
        actor = app.get_communicator_as_type("primary-btu", ApiBtuMeter)
        assert actor is not None
        monkeypatch.setattr(api_btu_meter, "time", clock)
        return Rig(app, actor, clock, omit="hp-ewt", channel="hp-ewt")
    app = make_app("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json")
    actor = app.get_communicator_as_type("tank1", ApiTankModule)
    assert actor is not None
    monkeypatch.setattr(api_tank_module, "time", clock)
    return Rig(app, actor, clock, omit="tank1-depth2", channel="tank1-depth2-device")


def test_one_quiet_channel_is_flatlined_and_the_pico_is_not_missing(rig: Rig) -> None:
    rig.run(5)
    assert rig.data.latest_channel_values[rig.channel] is not None
    rig.omitting = True
    rig.run(rig.quiet_seconds() + 30)
    quiet = [name for name in rig.flatlined() if name.startswith(rig.omit)]
    assert rig.channel in quiet
    assert len(quiet) == len(set(quiet))
    assert rig.flatlined() == quiet
    assert rig.missing() == []
    assert rig.data.latest_channel_values[rig.channel] is None


def test_a_channel_that_misses_one_post_is_not_flatlined(rig: Rig) -> None:
    rig.run(5)
    rig.omitting = True
    rig.run(rig.period_s)
    rig.omitting = False
    rig.run(rig.quiet_seconds())
    assert rig.flatlined() == []
    assert rig.data.latest_channel_values[rig.channel] is not None


def test_a_plant_that_stops_showing_a_pico_is_reported_once_and_not_channel_by_channel(
    rig: Rig,
) -> None:
    rig.run(20)
    rig.plant_shows = False
    rig.run(int(rig.actor.flatline_seconds()) + 40)
    assert len(rig.missing()) == 1
    flatlined = rig.flatlined()
    assert flatlined
    assert len(flatlined) == len(set(flatlined))
