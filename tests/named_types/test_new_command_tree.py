"""Tests new.command.tree type, version 000"""

from gwsproto.named_types import NewCommandTree


def test_new_command_tree_generated() -> None:
    d = {
        "FromGNodeAlias": "hw1.isone.me.versant.keene.fir.scada",
        "ShNodes": [ { "ActorClass": "Scada", "DisplayName": "Fir SCADA", "Name": "s", "ShNodeId": "bae076c2-05cb-40c8-996a-b1a7f642ccf7", "TypeName": "spaceheat.node.gt", "Version": "200" }, { "ActorClass": "Parentless", "DisplayName": "Secondary Scada", "Name": "s2", "ShNodeId": "57b027a6-f446-4403-bc69-26f56a1176bb", "TypeName": "spaceheat.node.gt", "Version": "200" }],
        "UnixMs": 1735861984823,
        "TypeName": "new.command.tree",
        "Version": "000",
    }

    d2 = NewCommandTree.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
