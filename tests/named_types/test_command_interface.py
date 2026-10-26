"""Tests gw.command.interface type, version 000: the sema example round-trips and
each axiom rejects its counterexample."""

import copy

from gwsproto.named_types import CommandInterface
from tests.named_types.sema_oracle import assert_refused

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


def test_gw_command_interface_axiom_1_empty_commands() -> None:
    d = copy.deepcopy(EXAMPLE)
    d["Commands"] = []
    assert_refused(CommandInterface, d, "Axiom 1")


def test_gw_command_interface_axiom_2_event_outside_vocabulary() -> None:
    d = copy.deepcopy(EXAMPLE)
    d["Commands"][0]["Event"] = "TurnSideways"
    assert_refused(CommandInterface, d, "Axiom 2")


def test_gw_command_interface_axiom_3_state_outside_vocabulary() -> None:
    d = copy.deepcopy(EXAMPLE)
    d["Commands"][0]["ToState"] = "HpSideways"
    assert_refused(CommandInterface, d, "Axiom 3")
