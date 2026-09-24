"""The power meter and the Hubitat actors report through glitches, never
problem events: a Warning for a field condition (the meter, the hub, the
network), an Error for the scada's own failure, each at most once per
condition per REPEAT_GLITCH_S."""
import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from gwproto import Message
from result import Err, Ok

from actors.glitch_limit import REPEAT_GLITCH_S, GlitchLimit
from actors.hubitat import Hubitat
from actors.hubitat_poller import HubitatRESTPoller
from actors.power_meter import PowerMeter, PowerMeterDriverThread
from drivers.driver_result import DriverResult
from gwproactor.message import InternalShutdownMessage
from gwsproto.enums import LogLevel, TelemetryName
from gwsproto.named_types import Glitch, SyncedReadings
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.type_helpers import MakerAPIAttributeGt
from tests.actors.test_pico_identity import PAIRS, boot

WILLOW = PAIRS["willow"]


def glitches(payloads: list[Any], level: LogLevel) -> list[Glitch]:
    """The Glitch payloads at `level`, after checking no payload is a
    problem event."""
    assert not any(getattr(p, "TypeName", "") == "gridworks.event.problem" for p in payloads), payloads
    return [p for p in payloads if isinstance(p, Glitch) and p.Type == level]


# ---- power meter -------------------------------------------------------


def meter_thread(tmp_path: Path) -> tuple[PowerMeterDriverThread, list[Message]]:
    app = boot(tmp_path, WILLOW, json.loads((Path(__file__).parent.parent / "config" / WILLOW[0]).read_text()))
    meter = app.get_communicator_as_type(CoreNodeNames.asset_power_meter, PowerMeter)
    assert meter is not None
    thread = meter._sync_thread
    assert isinstance(thread, PowerMeterDriverThread)
    queued: list[Message] = []
    thread._put_to_async_queue = queued.append
    return thread, queued


def payloads(queued: list[Message]) -> list[Any]:
    for m in queued:
        if isinstance(m.Payload, Glitch):
            assert m.Header.Dst == CoreNodeNames.primary_scada
    return [m.Payload for m in queued]


def test_meter_start_warnings_are_a_warning_glitch(tmp_path: Path) -> None:
    thread, queued = meter_thread(tmp_path)
    thread.driver.start = lambda: Ok(DriverResult(True, [RuntimeError("slow modbus")]))

    thread._preiterate()
    [glitch] = glitches(payloads(queued), LogLevel.Warning)
    assert glitch.Summary == "meter-start-warning"
    assert "slow modbus" in glitch.Details


def test_meter_start_error_is_a_warning_glitch_and_still_shuts_down(tmp_path: Path) -> None:
    thread, queued = meter_thread(tmp_path)
    thread.driver.start = lambda: Err(ConnectionError("no meter on the port"))

    thread._preiterate()
    [glitch] = glitches(payloads(queued), LogLevel.Warning)
    assert glitch.Summary == "meter-start-error"
    assert "no meter on the port" in glitch.Details
    assert any(isinstance(p, InternalShutdownMessage) for p in queued)


def test_meter_hw_uid_mismatch_is_a_warning_glitch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    thread, queued = meter_thread(tmp_path)
    monkeypatch.setattr(thread.driver.component.gt, "HwUid", "meter-in-layout")
    thread.driver.read_hw_uid = lambda: Ok(DriverResult("meter-on-the-wire"))

    thread._ensure_hardware_uid()
    [glitch] = glitches(payloads(queued), LogLevel.Warning)
    assert glitch.Summary == "meter-hw-uid-mismatch"
    assert "meter-on-the-wire" in glitch.Details


def test_meter_read_warnings_are_one_warning_glitch_a_day_per_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    thread, queued = meter_thread(tmp_path)
    thread.driver.read_telemetry_value = lambda ch: Ok(DriverResult(1000, [TimeoutError("read timed out")]))
    channels = len(thread.my_channels)

    for _ in range(3):
        thread.update_latest_value_dicts()
    found = glitches(payloads(queued), LogLevel.Warning)
    assert len(found) == channels
    assert {g.Summary for g in found} == {"meter-read-warning"}

    a_day_on = time.time() + REPEAT_GLITCH_S
    monkeypatch.setattr(time, "time", lambda: a_day_on)
    thread.update_latest_value_dicts()
    assert len(glitches(payloads(queued), LogLevel.Warning)) == 2 * channels


def test_a_synced_readings_failure_is_one_error_glitch(tmp_path: Path) -> None:
    thread, queued = meter_thread(tmp_path)
    ch = thread.my_channels[0]
    thread.latest_telemetry_value[ch] = None  # SyncedReadings refuses a None value

    for _ in range(2):
        thread.report_sampled_telemetry_values([ch])
    [glitch] = glitches(payloads(queued), LogLevel.Error)
    assert glitch.Summary == "meter-synced-readings"


# ---- Hubitat web listener ----------------------------------------------


class RawPost:
    def __init__(self, text: str) -> None:
        self.body = text

    async def text(self) -> str:
        return self.body


class UnreadablePost:
    async def text(self) -> str:
        raise ConnectionResetError("hub closed the connection")


def hubitat(tmp_path: Path) -> tuple[Hubitat, list[Message]]:
    """No sim pair boots a Hubitat; this one carries what the web handler reads."""
    app = boot(tmp_path, WILLOW, json.loads((Path(__file__).parent.parent / "config" / WILLOW[0]).read_text()))
    queued: list[Message] = []
    app.send_threadsafe = queued.append
    actor = Hubitat.__new__(Hubitat)
    actor._name = "hubitat"
    actor._services = app
    actor._report_dst = app.name
    actor._web_event_handlers = {}
    actor.glitch_limit = GlitchLimit(REPEAT_GLITCH_S)
    return actor, queued


def test_hubitat_unreadable_post_is_one_warning_glitch(tmp_path: Path) -> None:
    actor, queued = hubitat(tmp_path)

    for _ in range(2):
        asyncio.run(actor._handle_web_post(UnreadablePost()))
    [glitch] = glitches([m.Payload for m in queued], LogLevel.Warning)
    assert glitch.Summary == "hubitat-unreadable-post"


def test_hubitat_event_it_cannot_decode_is_one_warning_glitch(tmp_path: Path) -> None:
    actor, queued = hubitat(tmp_path)

    for _ in range(2):
        asyncio.run(actor._handle_web_post(RawPost('{"content": {"name": "temperature"}}')))
    [glitch] = glitches([m.Payload for m in queued], LogLevel.Warning)
    assert glitch.Summary == "hubitat-event-refused"


# ---- Hubitat poller ----------------------------------------------------


class Reply:
    def __init__(self, body: Any) -> None:
        self.body = body

    async def json(self, content_type: Any = None) -> Any:
        return self.body


def poller(tmp_path: Path, attributes: list[MakerAPIAttributeGt]) -> tuple[HubitatRESTPoller, list[Message]]:
    """No sim pair boots a Hubitat; this poller carries what the converter reads."""
    app = boot(tmp_path, WILLOW, json.loads((Path(__file__).parent.parent / "config" / WILLOW[0]).read_text()))
    forwarded: list[Message] = []
    p = HubitatRESTPoller.__new__(HubitatRESTPoller)
    p._name = "zone1-main-hubitat"
    p._report_dst = app.name
    p._scada_g_node_alias = app.hardware_layout.scada_g_node_alias
    p._component = SimpleNamespace(gt=SimpleNamespace(Poller=SimpleNamespace(attributes=attributes)))
    p._value_converters = {a.attribute_name: (lambda v: int(float(v) * 1000)) for a in attributes}
    p._forward = forwarded.append
    p.glitch_limit = GlitchLimit(REPEAT_GLITCH_S)
    return p, forwarded


def attribute(name: str, channel: str) -> MakerAPIAttributeGt:
    return MakerAPIAttributeGt(
        AttributeName=name,
        ChannelName=channel,
        NodeName="zone1-main",
        TelemetryName=TelemetryName.AirTempFTimes1000,
    )


def test_poller_reports_a_missing_attribute_even_when_another_converts(tmp_path: Path) -> None:
    p, forwarded = poller(
        tmp_path, [attribute("temperature", "zone1-main-temp"), attribute("heatingSetpoint", "zone1-main-set")]
    )
    reply = {"id": 7, "attributes": [{"name": "temperature", "currentValue": "68.5"}]}

    for _ in range(2):
        message = asyncio.run(p._hubitat_response_converter(Reply(reply)))
        assert message is not None and isinstance(message.Payload, SyncedReadings)
    [glitch] = glitches([m.Payload for m in forwarded], LogLevel.Warning)
    assert glitch.Summary == "hubitat-attribute"
    assert "heatingSetpoint" in glitch.Details


def test_poller_reply_it_cannot_decode_is_one_warning_glitch(tmp_path: Path) -> None:
    p, forwarded = poller(tmp_path, [attribute("temperature", "zone1-main-temp")])

    for _ in range(2):
        assert asyncio.run(p._hubitat_response_converter(Reply({"error": "hub busy"}))) is None
    [glitch] = glitches([m.Payload for m in forwarded], LogLevel.Warning)
    assert glitch.Summary == "hubitat-reply-refused"


def test_poller_convert_failures_are_one_warning_a_day_per_attribute(tmp_path: Path) -> None:
    p, forwarded = poller(tmp_path, [attribute("temperature", "zone1-main-temp")])

    for bad in ("warm", "cold"):
        reply = {"id": 7, "attributes": [{"name": "temperature", "currentValue": bad}]}
        asyncio.run(p._hubitat_response_converter(Reply(reply)))
    [glitch] = glitches([m.Payload for m in forwarded], LogLevel.Warning)
    assert glitch.Summary == "hubitat-attribute"
