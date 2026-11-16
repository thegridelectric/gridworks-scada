"""Tests fsm.atomic.report type, version 001"""

from gwsproto.enums import FsmReportType, MoveSiegValve, RelayEnergizationState
from gwsproto.named_types import FsmAtomicReport
from gwsproto.named_types.fsm_atomic_report import RelayPinSetAction

from tests.named_types.sema_oracle import assert_conforms, assert_refused

EVENT = {
    "MachineHandle": "auto.lc.n.sieg-loop",
    "StateEnum": "sieg.valve.state",
    "ReportType": "Event",
    "EventEnum": "move.sieg.valve",
    "Event": "MoveToFullKeep",
    "FromState": "FullySend",
    "ToState": "FullyKeep",
    "UnixTimeMs": 1794328024244,
    "TriggerId": "87d22291-5893-4bfb-8031-8c7c3d8c201a",
    "TypeName": "fsm.atomic.report",
    "Version": "001",
}

ACTION = {
    "MachineHandle": "auto.lc.n.sieg-loop.hp-loop-on-off-relay",
    "StateEnum": "relay.pin",
    "ReportType": "Action",
    "Action": {"Value": 1},
    "UnixTimeMs": 1794328024244,
    "TriggerId": "87d22291-5893-4bfb-8031-8c7c3d8c201a",
    "TypeName": "fsm.atomic.report",
    "Version": "001",
}


def test_an_event_report_with_its_event_conforms() -> None:
    assert_conforms(FsmAtomicReport.model_validate(EVENT))


def test_an_action_report_with_its_action_conforms() -> None:
    report = FsmAtomicReport.model_validate(ACTION)
    assert isinstance(report.Action, RelayPinSetAction)
    assert report.Action.Value == RelayEnergizationState.Energized
    assert_conforms(report)


def test_an_event_report_without_event_fields_fails_axiom_2() -> None:
    """The report the loop's own atomic once sent for a move the strategy
    chose: Event with no EventEnum or Event."""
    payload = {**EVENT}
    del payload["EventEnum"]
    del payload["Event"]
    assert_refused(FsmAtomicReport, payload, match="Axiom 2")


def test_an_action_report_with_event_fields_fails_axiom_2() -> None:
    payload = {
        **ACTION,
        "EventEnum": "change.relay.state",
        "Event": "CloseRelay",
        "FromState": "Open",
        "ToState": "Closed",
    }
    assert_refused(FsmAtomicReport, payload, match="Axiom 2")


def test_an_action_report_without_its_action_fails_axiom_1() -> None:
    payload = {**ACTION}
    del payload["Action"]
    assert_refused(FsmAtomicReport, payload, match="Axiom 1")


def test_an_event_report_with_an_action_fails_axiom_1() -> None:
    payload = {**EVENT, "Action": {"Value": 1}}
    assert_refused(FsmAtomicReport, payload, match="Axiom 1")


def test_the_loops_own_atomic_names_the_move_vocabulary() -> None:
    report = FsmAtomicReport.model_validate(EVENT)
    assert report.ReportType == FsmReportType.Event
    assert report.EventEnum == MoveSiegValve.enum_name()
    assert report.Event == MoveSiegValve.MoveToFullKeep
