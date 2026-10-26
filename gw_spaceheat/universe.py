"""Universe coherence guardrail (universe-guardrail spoke, OPS-407).

A GNode's *universe* is the first dotted segment of its alias (`d1`, `hw1`, the
single production `w…`); its *kind* is that segment's first letter — `d` dev,
`h` hybrid, `w` production. A rabbit broker names the same universe in its DNS
host (`hw1-1.electricity.works`) and its vhost (`hw1__1`), where the trailing
`-N` / `__N` is a broker/world-instance index, not part of the universe.

The scada talks MQTT and sees the broker *host*, so it checks its own alias
universe against the host's and refuses to boot on a mismatch (e.g. a `d1`
scada pointed at the `hw1` broker). The dev rabbit runs on `localhost` serving
the `d1` universe.

This is a *cooperative* check — it protects any client that runs it, which is
enough for honest misconfiguration. The hard boundary is server-side rabbit
permissions (gridworks-base); see the universe-guardrail spoke.
"""

DEV_LOCALHOST_UNIVERSE = "d1"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}


class UniverseMismatchError(Exception):
    """A GNode alias and the broker it would connect to are in different universes."""


def universe_of_alias(alias: str) -> str:
    """The universe of a GNodeAlias: its first dotted segment (`hw1.isone…` → `hw1`)."""
    return alias.split(".")[0]


def universe_of_host(host: str) -> str:
    """The universe a rabbit broker host serves: the first DNS label up to `-`
    (`hw1-1.electricity.works` → `hw1`). `localhost` is the dev rabbit → `d1`."""
    if host in _LOCAL_HOSTS:
        return DEV_LOCALHOST_UNIVERSE
    return host.split(".")[0].split("-")[0]


def assert_universe_coherence(aliases: dict[str, str], broker_host: str) -> None:
    """Raise `UniverseMismatchError` unless every alias shares the broker's universe.

    `aliases` maps a label (e.g. ``"scada"``) to a GNodeAlias. The broker's
    universe is derived from `broker_host` (with `localhost ⇒ d1`)."""
    broker_universe = universe_of_host(broker_host)
    mismatched = {
        label: alias
        for label, alias in aliases.items()
        if universe_of_alias(alias) != broker_universe
    }
    if mismatched:
        detail = ", ".join(
            f"{label}={alias!r} (universe {universe_of_alias(alias)!r})"
            for label, alias in sorted(mismatched.items())
        )
        raise UniverseMismatchError(
            f"Universe mismatch: broker host {broker_host!r} serves universe "
            f"{broker_universe!r}, but these GNode aliases do not match: {detail}. "
            f"A GNode may only talk on a broker in its own universe."
        )
