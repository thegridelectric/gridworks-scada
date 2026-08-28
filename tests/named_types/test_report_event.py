"""Tests report.event type, version 004"""

import pytest

from gwsproto.named_types import ReportEvent

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
    with pytest.raises(ValueError, match="Axiom 1"):
        ReportEvent.model_validate(
            report_event(message_id="7c8a27f4-2bbd-4a6f-9d2c-1f0f4d6b7e21")
        )


def test_report_event_axiom_2() -> None:
    """TimeCreatedMs SHALL equal Report.MessageCreatedMs."""
    with pytest.raises(ValueError, match="Axiom 2"):
        ReportEvent.model_validate(report_event(time_created_ms=CREATED_MS + 1))


def test_report_event_axiom_3() -> None:
    """Src SHALL equal Report.FromGNodeAlias."""
    with pytest.raises(ValueError, match="Axiom 3"):
        ReportEvent.model_validate(report_event(src="hw1.isone.me.versant.keene.oak.scada"))
