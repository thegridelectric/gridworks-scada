"""Tests report.event type, version 004"""

from gwsproto.named_types import Report, ReportEvent
from tests.named_types.sema_oracle import assert_refused

SCADA = "hw1.isone.me.versant.keene.spruce.scada"


REPORT_ID = "ad65b1f0-7423-4a49-bf18-d2139dbe87f0"
CREATED_MS = 1775218866988


def report_event(
    src: str = SCADA, message_id: str = REPORT_ID, time_created_ms: int = CREATED_MS
) -> dict:
    return {
        "MessageId": message_id,
        "TimeCreatedMs": time_created_ms,
        "Src": src,
        "Report": {
            "FromGNodeAlias": SCADA,
            "FromGNodeInstanceId": "7f56f328-54bd-49eb-b90e-c3ac15501ff1",
            "AboutGNodeAlias": "d1.isone.me.versant.keene.spruce",
            "SlotStartUnixS": 1775218800,
            "SlotDurationS": 300,
            "ChannelReadingList": [],
            "StateList": [],
            "FsmReportList": [],
            "MessageCreatedMs": CREATED_MS,
            "Id": REPORT_ID,
            "TypeName": "report",
            "Version": "003",
        },
        "TypeName": "report.event",
        "Version": "004",
    }


def test_report_event_generated() -> None:
    d = report_event()
    assert ReportEvent.model_validate(d).model_dump(exclude_none=True) == d


def test_report_event_axiom_1() -> None:
    """MessageId SHALL equal Report.Id."""
    assert_refused(
        ReportEvent,
        report_event(message_id="7c8a27f4-2bbd-4a6f-9d2c-1f0f4d6b7e21"),
        match="Axiom 1",
    )


def test_report_event_axiom_2() -> None:
    """TimeCreatedMs SHALL equal Report.MessageCreatedMs."""
    assert_refused(
        ReportEvent, report_event(time_created_ms=CREATED_MS + 1), match="Axiom 2"
    )


def test_report_event_axiom_3() -> None:
    """Src SHALL equal Report.FromGNodeAlias."""
    assert_refused(
        ReportEvent,
        report_event(src="hw1.isone.me.versant.keene.oak.scada"),
        match="Axiom 3",
    )


def test_envelope_required_on_decode_derived_on_construction() -> None:
    d = report_event()
    for field in ("MessageId", "TimeCreatedMs", "Src"):
        assert_refused(
            ReportEvent, {k: v for k, v in d.items() if k != field}, match=field
        )
    ev = ReportEvent(Report=Report.model_validate(d["Report"]))
    assert ev.model_dump(exclude_none=True) == d
