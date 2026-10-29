"""Tests scada.control.capabilities type, version 003: the sema example round-trips
and each axiom rejects its counterexample. The example is a Nolan-shaped cover
with admin holding the tree: a relay under admin, the cycler's vdc relay under
the cycler under five-v-boss, the secondary pump under hp-boss with an
interface admin may take, a DAC, and the two interior command nodes
(five-v-boss with its two vocabularies, hp-boss)."""

import copy

from gwsproto.named_types import ScadaControlCapabilities
from tests.named_types.sema_oracle import assert_refused

EXAMPLE = {'CommandInterfaces': [{'ActorName': 'zone1-bedrooms-ops-relay',
                        'AdminMayTake': False,
                        'Commands': [{'Event': 'CloseRelay',
                                      'ToState': 'RelayClosed',
                                      'TypeName': 'gw.command.transition',
                                      'Version': '000'},
                                     {'Event': 'OpenRelay',
                                      'ToState': 'RelayOpen',
                                      'TypeName': 'gw.command.transition',
                                      'Version': '000'}],
                        'EventType': 'change.relay.state',
                        'StateType': 'relay.closed.or.open',
                        'TypeName': 'gw.command.interface',
                        'Version': '001'},
                       {'ActorName': 'five-v-boss',
                        'AdminMayTake': False,
                        'Commands': [{'Event': 'TurnOff',
                                      'ToState': 'FiveVOff',
                                      'TypeName': 'gw.command.transition',
                                      'Version': '000'},
                                     {'Event': 'TurnOn',
                                      'ToState': 'PicoCycler',
                                      'TypeName': 'gw.command.transition',
                                      'Version': '000'}],
                        'EventType': 'turn.5v.on.off',
                        'StateType': 'five.v.boss.state',
                        'TypeName': 'gw.command.interface',
                        'Version': '001'},
                       {'ActorName': 'five-v-boss',
                        'AdminMayTake': False,
                        'Commands': [{'Event': 'RebootPicos',
                                      'ToState': 'PicoCycler',
                                      'TypeName': 'gw.command.transition',
                                      'Version': '000'}],
                        'EventType': 'reboot.picos',
                        'StateType': 'five.v.boss.state',
                        'TypeName': 'gw.command.interface',
                        'Version': '001'},
                       {'ActorName': 'hp-boss',
                        'AdminMayTake': False,
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
                        'Version': '001'},
                       {'ActorName': 'secondary-pump-relay',
                        'AdminMayTake': True,
                        'Commands': [{'Event': 'CloseRelay',
                                      'ToState': 'RelayClosed',
                                      'TypeName': 'gw.command.transition',
                                      'Version': '000'},
                                     {'Event': 'OpenRelay',
                                      'ToState': 'RelayOpen',
                                      'TypeName': 'gw.command.transition',
                                      'Version': '000'}],
                        'EventType': 'change.relay.state',
                        'StateType': 'relay.closed.or.open',
                        'TypeName': 'gw.command.interface',
                        'Version': '001'}],
 'CommandNodes': [{'ActorClass': 'FiveVBoss',
                   'ActorHierarchyName': 's.five-v-boss',
                   'DisplayName': 'Five V Boss',
                   'Handle': 'admin.five-v-boss',
                   'Name': 'five-v-boss',
                   'ShNodeId': 'f7d2e5a9-1b4c-4a8e-9d3f-6c0b2e8a4d1f',
                   'TypeName': 'spaceheat.node.gt',
                   'Version': '303'},
                  {'ActorClass': 'HpBoss',
                   'ActorHierarchyName': 's.hp-boss',
                   'DisplayName': 'Heat Pump Boss',
                   'Handle': 'admin.hp-boss',
                   'Name': 'hp-boss',
                   'ShNodeId': '0a3c5e7f-9b1d-4f2a-8e6c-4d7b9a1c3e5f',
                   'TypeName': 'spaceheat.node.gt',
                   'Version': '303'}],
 'ControlChannels': [{'AboutNodeName': 'zone1-bedrooms-ops-relay',
                      'CapturedByNodeName': 'zone1-bedrooms-ops-relay',
                      'DisplayName': 'Zone 1 Bedrooms Ops Relay State',
                      'Id': '9c33d7af-59e0-415b-8208-ecf64916a64b',
                      'Name': 'zone1-bedrooms-ops-relay',
                      'Quantity': 'Unitless',
                      'TelemetryName': 'RelayState',
                      'TerminalAssetAlias': 'hw1.isone.me.versant.keene.beech.ta',
                      'TypeName': 'data.channel.gt',
                      'Version': '004'},
                     {'AboutNodeName': 'vdc-relay',
                      'CapturedByNodeName': 'vdc-relay',
                      'DisplayName': '5VDC Relay State',
                      'Id': '2b8e4d6f-7a1c-4e9b-8d3f-5c0a2e4b6d8f',
                      'Name': 'vdc-relay',
                      'Quantity': 'Unitless',
                      'TelemetryName': 'RelayState',
                      'TerminalAssetAlias': 'hw1.isone.me.versant.keene.beech.ta',
                      'TypeName': 'data.channel.gt',
                      'Version': '004'},
                     {'AboutNodeName': 'secondary-pump-relay',
                      'CapturedByNodeName': 'secondary-pump-relay',
                      'DisplayName': 'Secondary Pump Relay State',
                      'Id': '7e1a3c5b-9d2f-4b8e-a6c4-0f3d5b7e9a1c',
                      'Name': 'secondary-pump-relay',
                      'Quantity': 'Unitless',
                      'TelemetryName': 'RelayState',
                      'TerminalAssetAlias': 'hw1.isone.me.versant.keene.beech.ta',
                      'TypeName': 'data.channel.gt',
                      'Version': '004'},
                     {'AboutNodeName': 'secondary-010v',
                      'CapturedByNodeName': 'secondary-010v',
                      'DisplayName': 'Secondary Pump 0-10V',
                      'Id': '4d0f6a8c-9b2e-4c1d-a7f5-3e8b0d2c4a6e',
                      'Name': 'secondary-010v',
                      'Quantity': 'Voltage',
                      'TelemetryName': 'VoltsTimesTen',
                      'TerminalAssetAlias': 'hw1.isone.me.versant.keene.beech.ta',
                      'TypeName': 'data.channel.gt',
                      'Version': '004'}],
 'DacNodes': [{'ActorClass': 'ZeroTenOutputer',
               'ActorHierarchyName': 's.secondary-010v',
               'ComponentId': '3b9f2c7d-5e1a-4d8b-a6c3-9f0e2d4b6a8c',
               'DisplayName': 'Secondary Pump 0-10V',
               'Handle': 'admin.secondary-010v',
               'Name': 'secondary-010v',
               'ShNodeId': 'e4a1c6b8-3d2f-4b9a-8c7e-1f5d3a9b0c2e',
               'TypeName': 'spaceheat.node.gt',
               'Version': '303'}],
 'FromGNodeAlias': 'hw1.isone.me.versant.keene.beech.scada',
 'MessageCreatedMs': 1757286000000,
 'RelayNodes': [{'ActorClass': 'Relay',
                 'ActorHierarchyName': 's.zone1-bedrooms-ops-relay',
                 'ComponentId': '25f344ee-39ea-4904-bff9-54f2022337af',
                 'DisplayName': 'Zone 1 Bedrooms Ops Relay',
                 'Handle': 'admin.zone1-bedrooms-ops-relay',
                 'Name': 'zone1-bedrooms-ops-relay',
                 'ShNodeId': 'a7f4becc-8e35-4118-a3e9-ab6ad13f5a67',
                 'TypeName': 'spaceheat.node.gt',
                 'Version': '303'},
                {'ActorClass': 'Relay',
                 'ActorHierarchyName': 's.vdc-relay',
                 'ComponentId': '6d1c8a1e-2f4b-4c7a-9e3d-0b5a7c2e4f61',
                 'DisplayName': '5VDC Relay',
                 'Handle': 'admin.five-v-boss.pico-cycler.vdc-relay',
                 'Name': 'vdc-relay',
                 'ShNodeId': 'c2e7b9d4-8a1f-4e6b-b3c5-7d9e1f0a2b4c',
                 'TypeName': 'spaceheat.node.gt',
                 'Version': '303'},
                {'ActorClass': 'Relay',
                 'ActorHierarchyName': 's.secondary-pump-relay',
                 'ComponentId': '6d1c8a1e-2f4b-4c7a-9e3d-0b5a7c2e4f61',
                 'DisplayName': 'Secondary Pump Relay',
                 'Handle': 'admin.hp-boss.secondary-pump-relay',
                 'Name': 'secondary-pump-relay',
                 'ShNodeId': '5b1d7e2a-4c9f-4a3e-8d6b-2f0c4e8a1b3d',
                 'TypeName': 'spaceheat.node.gt',
                 'Version': '303'}],
 'TypeName': 'scada.control.capabilities',
 'Version': '003'}


def test_scada_control_capabilities_example_round_trips() -> None:
    assert ScadaControlCapabilities.model_validate(EXAMPLE).model_dump(by_alias=True, exclude_none=True) == EXAMPLE


def test_scada_control_capabilities_axiom_1_c_relay_class_in_command_nodes() -> None:
    d = copy.deepcopy(EXAMPLE)
    d["CommandNodes"][0]["ActorClass"] = "Relay"
    assert_refused(ScadaControlCapabilities, d, "Axiom 1")


def test_scada_control_capabilities_axiom_2_command_node_handle_terminal() -> None:
    d = copy.deepcopy(EXAMPLE)
    d["CommandNodes"][0]["Handle"] = "admin.cycler"
    assert_refused(ScadaControlCapabilities, d, "Axiom 2")


def test_scada_control_capabilities_axiom_3_channel_about_unknown_node() -> None:
    d = copy.deepcopy(EXAMPLE)
    d["ControlChannels"][0]["AboutNodeName"] = "hp-boss"
    assert_refused(ScadaControlCapabilities, d, "Axiom 3")


def test_scada_control_capabilities_axiom_4_a_directly_commanded_without_interface() -> None:
    d = copy.deepcopy(EXAMPLE)
    d["CommandInterfaces"] = [i for i in d["CommandInterfaces"] if i["ActorName"] != "hp-boss"]
    assert_refused(ScadaControlCapabilities, d, "Axiom 4")


def test_scada_control_capabilities_axiom_4_a_owned_relay_with_interface() -> None:
    """The vdc relay sits under the cycler, so an interface for it is extra."""
    d = copy.deepcopy(EXAMPLE)
    relay = copy.deepcopy(d["CommandInterfaces"][0])
    relay["ActorName"] = "vdc-relay"
    d["CommandInterfaces"].append(relay)
    assert_refused(ScadaControlCapabilities, d, "Axiom 4")


def test_scada_control_capabilities_axiom_4_a_owned_relay_admin_may_not_take() -> None:
    """The pump sits under hp-boss; its interface is in the cover only
    through AdminMayTake."""
    d = copy.deepcopy(EXAMPLE)
    for i in d["CommandInterfaces"]:
        if i["ActorName"] == "secondary-pump-relay":
            i["AdminMayTake"] = False
    assert_refused(ScadaControlCapabilities, d, "Axiom 4")


def test_scada_control_capabilities_axiom_4_b_duplicate_actor_name() -> None:
    d = copy.deepcopy(EXAMPLE)
    d["CommandInterfaces"].append(copy.deepcopy(d["CommandInterfaces"][0]))
    assert_refused(ScadaControlCapabilities, d, "Axiom 4")


def test_scada_control_capabilities_axiom_4_c_admin_may_take_a_command_node() -> None:
    d = copy.deepcopy(EXAMPLE)
    for i in d["CommandInterfaces"]:
        if i["ActorName"] == "hp-boss":
            i["AdminMayTake"] = True
    assert_refused(ScadaControlCapabilities, d, "Axiom 4")
