"""Tests new.command.tree type, version 002"""

import pytest

from gwsproto.named_types import NewCommandTree


def node(name: str, handle: str | None, actor_class: str = "NoActor") -> dict:
    d = {
        "Name": name,
        "ActorClass": actor_class,
        "ShNodeId": "6c734dbb-9950-485d-a83b-55456d914576",
        "TypeName": "spaceheat.node.gt",
        "Version": "302",
    }
    if handle is not None:
        d["Handle"] = handle
    if actor_class != "NoActor":
        d["ActorHierarchyName"] = f"s.{name}"
    return d


def tree(nodes: list[dict]) -> dict:
    return {
        "FromGNodeAlias": "d1.isone.me.versant.keene.spruce.scada",
        "ShNodes": nodes,
        "UnixMs": 1731168353695,
        "TypeName": "new.command.tree",
        "Version": "002",
    }


def test_new_command_tree_generated() -> None:
    d = {
        "FromGNodeAlias": "hw1.isone.me.versant.keene.fir.scada",
        "ShNodes": [
            {
                "ActorClass": "PrimaryScada",
                "DisplayName": "Fir SCADA",
                "Name": "s",
                "ShNodeId": "bae076c2-05cb-40c8-996a-b1a7f642ccf7",
                "TypeName": "spaceheat.node.gt",
                "Version": "302",
            },
            {
                "ActorClass": "SecondaryScada",
                "DisplayName": "Secondary Scada",
                "Name": "s2",
                "ShNodeId": "57b027a6-f446-4403-bc69-26f56a1176bb",
                "TypeName": "spaceheat.node.gt",
                "Version": "302",
            },
        ],
        "UnixMs": 1735861984823,
        "TypeName": "new.command.tree",
        "Version": "002",
    }

    d2 = NewCommandTree.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d


def test_new_command_tree_generated_handles() -> None:
    d = tree(
        [
            node("auto", "auto"),
            node("pico-cycler", "auto.pico-cycler", "PicoCycler"),
            node("vdc-relay", "auto.pico-cycler.vdc-relay", "Relay"),
        ]
    )
    d2 = NewCommandTree.model_validate(d).model_dump(exclude_none=True)
    assert d2 == d


def test_new_command_tree_axiom_1() -> None:
    """An effective handle whose prefix names no ShNode is rejected."""
    orphan = tree(
        [
            node("auto", "auto"),
            node("vdc-relay", "auto.pico-cycler.vdc-relay", "Relay"),
        ]
    )
    with pytest.raises(ValueError, match="Axiom 1"):
        NewCommandTree.model_validate(orphan)


def test_new_command_tree_axiom_1_handle_absent_root() -> None:
    """A Handle-absent node's effective handle is its Name, so it can anchor
    children (the `ltn` root anchoring `ltn.la`)."""
    d = tree([node("ltn", None), node("la", "ltn.la", "LeafAlly")])
    NewCommandTree.model_validate(d)
    # ... but a Handle-absent node anchors only under its own Name.
    d = tree([node("ltn", None), node("la", "ltn.x.la", "LeafAlly")])
    with pytest.raises(ValueError, match="Axiom 1"):
        NewCommandTree.model_validate(d)
