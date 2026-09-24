"""A BTU meter pico drops a thermistor at its rails before it posts, so the
scada sees an absent channel, never a bad one; a thermistor near a rail
gets past the pico's guard as an impossible temperature. The actor reports
both as one Warning glitch a day per channel: an implausible reading is
dropped from the readings it sends, and a channel that stops arriving
while its siblings keep posting is named once, alongside the
ChannelFlatlined the scada already gets each minute. The BTU meter is the
Nolan sim's primary-btu restated as a real pico."""

import time
from pathlib import Path

import pytest

import actors.api_btu_meter as api_btu_meter
import actors.glitch_limit as glitch_limit
from actors.api_btu_meter import ApiBtuMeter, IMPLAUSIBLE_BELOW_C, IMPLAUSIBLE_ABOVE_C
from actors.glitch_limit import REPEAT_GLITCH_S
from actors.pico_liveness import PicoLiveness
from gwsproto.enums import LogLevel
from gwsproto.named_types import ChannelFlatlined, Glitch, MultichannelSnapshot, SyncedReadings
from tests.actors.test_pico_channel_liveness import Clock
from tests.actors.test_pico_identity import PAIRS, boot, capture_sends, with_real_pico


def btu_actor(tmp_path: Path) -> ApiBtuMeter:
    pair = PAIRS["nolan"]
    app = boot(tmp_path, pair, with_real_pico(pair, "primary-btu", "HwUid"))
    actor = app.get_communicator_as_type("primary-btu", ApiBtuMeter)
    assert actor is not None
    return actor


def snapshot(actor: ApiBtuMeter, hot_c_x100: int, cold_c_x100: int = 4000) -> MultichannelSnapshot:
    assert actor.pico_uid
    return MultichannelSnapshot(
        HwUid=actor.pico_uid,
        ChannelNameList=[actor.flow_channel.Name, actor.hot_temp_channel.Name, actor.cold_temp_channel.Name],
        MeasurementList=[400, hot_c_x100, cold_c_x100],
        UnitList=["GpmTimes100", "CelsiusTimes100", "CelsiusTimes100"],
    )


def warnings(sent: list) -> list[Glitch]:
    return [p for p in sent if isinstance(p, Glitch) and p.Type == LogLevel.Warning]


def readings(sent: list) -> list[SyncedReadings]:
    return [p for p in sent if isinstance(p, SyncedReadings)]


@pytest.mark.parametrize("hot_c_x100", [int(IMPLAUSIBLE_BELOW_C * 100) - 1, int(IMPLAUSIBLE_ABOVE_C * 100) + 1])
def test_an_implausible_temperature_is_one_warning_a_day_and_no_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hot_c_x100: int
) -> None:
    actor = btu_actor(tmp_path)
    clock = Clock(time.time())
    monkeypatch.setattr(api_btu_meter, "time", clock)
    monkeypatch.setattr(glitch_limit, "time", clock)
    sent = capture_sends(actor)
    hot = actor.hot_temp_channel.Name

    actor._process_multichannel_snapshot(snapshot(actor, hot_c_x100))
    actor._process_multichannel_snapshot(snapshot(actor, hot_c_x100))
    [glitch] = warnings(sent)
    assert glitch.Summary == "open-thermistor"
    assert hot in glitch.Details
    for r in readings(sent):
        assert hot not in r.ChannelNameList
        assert actor.cold_temp_channel.Name in r.ChannelNameList

    # a plausible reading goes out again; implausible again the same day is silent
    actor._process_multichannel_snapshot(snapshot(actor, 5000))
    assert hot in readings(sent)[-1].ChannelNameList
    actor._process_multichannel_snapshot(snapshot(actor, hot_c_x100))
    assert len(warnings(sent)) == 1

    clock.now += REPEAT_GLITCH_S
    actor._process_multichannel_snapshot(snapshot(actor, hot_c_x100))
    assert len(warnings(sent)) == 2


def test_a_channel_the_pico_stops_posting_is_one_warning_a_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = btu_actor(tmp_path)
    clock = Clock(time.time())
    monkeypatch.setattr(api_btu_meter, "time", clock)
    monkeypatch.setattr(glitch_limit, "time", clock)
    sent = capture_sends(actor)
    hot = actor.hot_temp_channel.Name
    period = actor.layout.capture_tuning_by_channel[hot].CapturePeriodS
    quiet_s = int(period * PicoLiveness.MISSING_MULTIPLE) + 30

    def run(seconds: int, hot_posts: bool) -> None:
        for second in range(seconds):
            clock.now += 1
            if second % period == 0:
                reading = snapshot(actor, 5000)
                if not hot_posts:
                    reading = api_btu_meter.snapshot_without(reading, {hot})
                actor._process_multichannel_snapshot(reading)
            if second % 10 == 0:
                actor.check_liveness()

    run(period + 1, hot_posts=True)
    assert warnings(sent) == []

    run(quiet_s, hot_posts=False)
    [glitch] = warnings(sent)
    assert glitch.Summary == "quiet-channel"
    assert hot in glitch.Details
    assert [p.Channel.Name for p in sent if isinstance(p, ChannelFlatlined)].count(hot) >= 1

    run(quiet_s, hot_posts=False)
    assert len(warnings(sent)) == 1

    clock.now += REPEAT_GLITCH_S
    run(quiet_s, hot_posts=False)
    assert len(warnings(sent)) == 2
