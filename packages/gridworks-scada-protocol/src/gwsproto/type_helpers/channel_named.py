from typing import Protocol, runtime_checkable


@runtime_checkable
class ChannelNamed(Protocol):
    """Structural marker for a ConfigList entry that names a channel (e.g.
    relay.control.config, ads.channel.config, dac.output.config) — as
    opposed to one that doesn't. Not a shared base class: each
    config's own form is unrelated to every other's; this is a pure runtime
    isinstance check, not inheritance."""

    ChannelName: str
