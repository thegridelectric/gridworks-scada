"""Tests gw.command.interface type, version 000: the sema example round-trips and
each axiom rejects its counterexample."""

import copy

import pytest
from gwsproto.named_types import CommandInterface
from pydantic import ValidationError

EXAMPLE = {'ActorName': 'hp-boss',
 'Commands': [{'Event': 'TurnOn',
               'ToState': 'HpOn',
               'TypeName': 'gw.command.transition',
               'Version': '000'},
              {'Event': 'TurnOff',
               'ToState': 'HpOff',
               'TypeName': 'gw.command.transition',
               'Version': '000'}],
 'EventType': 'turn.hp.on.off',
 'StateType': 'hp.boss.state',
 'TypeName': 'gw.command.interface',
 'Version': '000'}


def test_gw_command_interface_generated() -> None:
    d2 = CommandInterface.model_validate(EXAMPLE).model_dump(exclude_none=True)
    assert d2 == EXAMPLE


def test_gw_command_interface_axiom_1_empty_commands() -> None:
    d = copy.deepcopy(EXAMPLE)
    d["Commands"] = []
    with pytest.raises(ValidationError, match="Axiom 1"):
        CommandInterface.model_validate(d)


def test_gw_command_interface_axiom_2_event_outside_vocabulary() -> None:
    d = copy.deepcopy(EXAMPLE)
    d["Commands"][0]["Event"] = "TurnSideways"
    with pytest.raises(ValidationError, match="Axiom 2"):
        CommandInterface.model_validate(d)


def test_gw_command_interface_axiom_3_state_outside_vocabulary() -> None:
    d = copy.deepcopy(EXAMPLE)
    d["Commands"][0]["ToState"] = "HpSideways"
    with pytest.raises(ValidationError, match="Axiom 3"):
        CommandInterface.model_validate(d)
