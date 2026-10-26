"""Tests gw.state.machine type, version 000"""

from gwsproto.named_types import GwStateMachine
from tests.named_types.sema_oracle import assert_conforms, assert_refused


def base() -> dict:
    return {
        "NodeName": "hp-boss",
        "StateEnum": "hp.boss.state",
        "StateEnumVersion": "000",
        "TypeName": "gw.state.machine",
        "Version": "000",
    }


def test_gw_state_machine_generated() -> None:
    d = base()
    t = GwStateMachine.model_validate(d)
    assert t.model_dump(exclude_none=True) == d
    assert_conforms(t)


def test_gw_state_machine_version_is_three_digits() -> None:
    for bad in ("13", "0013", "v013", "01a"):
        assert_refused(GwStateMachine, {**base(), "StateEnumVersion": bad})
