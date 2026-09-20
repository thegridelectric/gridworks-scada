"""The channel integrity axiom bodies the layout words share."""

from typing import Any, Iterable

from gwsproto.enums import ActorClass


def check_derived_channel_creator_resolution(
    sh_nodes: Iterable[Any],
    derived_channels: Iterable[Any],
    label: str,
) -> None:
    """a. Every DerivedChannel's CreatedByNodeName is the Name of a ShNode.
    b. That node's ActorClass is not NoActor."""
    actor_class_by_name = {n.Name: n.ActorClass for n in sh_nodes}
    for channel in derived_channels:
        if channel.CreatedByNodeName not in actor_class_by_name:
            raise ValueError(
                f"{label} failed (a): DerivedChannel {channel.Name!r} names "
                f"CreatedByNodeName {channel.CreatedByNodeName!r}, which is not "
                "a ShNode in ShNodes."
            )
        if actor_class_by_name[channel.CreatedByNodeName] == ActorClass.NoActor:
            raise ValueError(
                f"{label} failed (b): DerivedChannel {channel.Name!r} is created "
                f"by {channel.CreatedByNodeName!r}, whose ActorClass is NoActor."
            )


def check_data_channel_node_resolution(
    sh_nodes: Iterable[Any],
    data_channels: Iterable[Any],
    label: str,
) -> None:
    """a. Every DataChannel's AboutNodeName is the Name of a ShNode.
    b. So is its CapturedByNodeName.
    c. The capturing node's ActorClass is not NoActor."""
    actor_class_by_name = {n.Name: n.ActorClass for n in sh_nodes}
    for channel in data_channels:
        if channel.AboutNodeName not in actor_class_by_name:
            raise ValueError(
                f"{label} failed (a): DataChannel {channel.Name!r} names "
                f"AboutNodeName {channel.AboutNodeName!r}, which is not a "
                "ShNode in ShNodes."
            )
        if channel.CapturedByNodeName not in actor_class_by_name:
            raise ValueError(
                f"{label} failed (b): DataChannel {channel.Name!r} names "
                f"CapturedByNodeName {channel.CapturedByNodeName!r}, which is "
                "not a ShNode in ShNodes."
            )
        if actor_class_by_name[channel.CapturedByNodeName] == ActorClass.NoActor:
            raise ValueError(
                f"{label} failed (c): DataChannel {channel.Name!r} is captured "
                f"by {channel.CapturedByNodeName!r}, whose ActorClass is NoActor."
            )


def check_derived_channel_inputs_acyclic(
    data_channels: Iterable[Any],
    derived_channels: Iterable[Any],
    label: str,
) -> None:
    """a. Every DerivedChannel input names a DataChannel or a DerivedChannel.
    b. No DerivedChannel is reachable from itself through InputChannelNames."""
    data_names = {c.Name for c in data_channels}
    inputs_by_name = {c.Name: list(c.InputChannelNames) for c in derived_channels}
    for name, inputs in inputs_by_name.items():
        for input_name in inputs:
            if input_name not in data_names and input_name not in inputs_by_name:
                raise ValueError(
                    f"{label} failed (a): DerivedChannel {name!r} names input "
                    f"{input_name!r}, which is not a channel in DataChannels or "
                    "DerivedChannels."
                )
    for start in inputs_by_name:
        seen: set[str] = set()
        frontier = [n for n in inputs_by_name[start] if n in inputs_by_name]
        while frontier:
            current = frontier.pop()
            if current == start:
                raise ValueError(
                    f"{label} failed (b): DerivedChannel {start!r} is reachable "
                    "from itself through InputChannelNames."
                )
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(n for n in inputs_by_name[current] if n in inputs_by_name)


def check_channel_name_uniqueness(
    data_channels: Iterable[Any],
    derived_channels: Iterable[Any],
    label: str,
) -> None:
    """Channel Names are pairwise distinct across DataChannels and
    DerivedChannels together."""
    seen: set[str] = set()
    for name in [c.Name for c in data_channels] + [c.Name for c in derived_channels]:
        if name in seen:
            raise ValueError(
                f"{label} failed: more than one channel in DataChannels and "
                f"DerivedChannels is named {name!r}."
            )
        seen.add(name)
