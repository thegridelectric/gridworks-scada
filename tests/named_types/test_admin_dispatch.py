"""Tests admin.dispatch type, version 000"""

from gwsproto.named_types import AdminDispatch


def test_admin_dispatch_generated() -> None:
    d = {
        "DispatchTrigger": { "FromHandle": "h.s.admin", "ToHandle": "h.s.admin.iso-valve", "EventType": "change.valve.state", "EventName": "OpenValve", "TriggerId": "12da4269-63c3-44f4-ab65-3ee5e29329fe", "SendTimeUnixMs": 1709923791330, "TypeName": "fsm.event", "Version": "000", },
        "TimeoutSeconds": 300,
        "TypeName": "admin.dispatch",
        "Version": "000",
    }

    d2 = AdminDispatch.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
