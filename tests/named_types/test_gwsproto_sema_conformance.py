"""gwsproto ↔ sema conformance — the standing regression test.

gwsproto types/enums/property-formats are hand-written twins of sema vocabulary;
sema is the contract. This test runs the conformance sweep
(`gwsproto_sema_conformance.run`) against the sibling `sema` checkout and fails
on ANY new drift: a type/enum pinned off sema's latest version, a canonical sema
example gwsproto rejects, a non-canonical re-dump, an enum value set that differs
from sema's, or a property format that accepts a counterexample / rejects a valid
example.

The allowlists below are the checked-in record of KNOWN gaps. Two kinds:

- NO_WORD_* — gwsproto vocabulary with no sema word yet (legitimately
  gwsproto-only, e.g. LTN/market/admin types not modelled in sema). Adding one
  to sema means REMOVING it here; a new gwsproto-only word means ADDING it here
  (a deliberate, reviewed act).
- KNOWN_*_DRIFT — real conformance debt to burn down (gwsproto pinned off sema's
  latest, or a format validator bug). Fix the gwsproto side, then remove the
  entry. These are NOT acceptable long-term; the list should shrink to empty.

The sets are matched EXACTLY, so the test fails both when a NEW gap appears and
when a listed gap is fixed but not removed here — keeping the record honest.

Requires the sibling sema checkout (read as the contract). Skips if absent
(e.g. a scada-only CI checkout); enforce it where both repos are present.
"""

import sys
from pathlib import Path

import pytest

# The conformance tool lives at the package root (dev/CI tooling, not shipped
# in the importable package), so put it on the path before importing.
_PKG = Path(__file__).resolve().parents[2] / "packages" / "gridworks-scada-protocol"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

import gwsproto_sema_conformance as conformance  # noqa: E402

SEMA_ROOT = conformance.DEFAULT_SEMA

# --- gwsproto vocabulary with no sema word yet (gwsproto-only) ---
NO_WORD_TYPES = {
    "actuators.ready",
    "admin.analog.dispatch",
    "admin.dispatch",
    "admin.keep.alive",
    "admin.release.control",
    "ally.gives.up",
    "analog.dispatch",
    "async.btu.params",
    "baseurl.failure.alert",
    "bid.recommendation",
    "channel.flatlined",
    "dispatch.contract.go.dormant",
    "dispatch.contract.go.live",
    "flo.next.hour.plans",
    "flo.params",
    "go.dormant",
    "hack.oil.off",
    "hack.oil.on",
    "market.maker.ack",
    "microvolts",
    "multichannel.snapshot",
    "no.new.contract.warning",
    "pico.comms.params",
    "pico.missing",
    "remaining.elec",
    "remaining.elec.event",
    "reset.hp.keep.value",
    "send.snap",
    "set.lwt.control.params",
    "set.target.lwt",
    "sieg.loop.endpoint.valve.adjustment",
    "sieg.target.too.low",
    "slow.contract.heartbeat",
    "slow.dispatch.contract",
    "suit.up",
    "tank.module.params",
    "wake.up",
}

NO_WORD_ENUMS = {
    "aquastat.control.state",
    "change.aquastat.control",
    "change.heat.pump.control",
    "change.keep.send",
    "change.primary.pump.control",
    "change.store.flow.relay",
    "flow.manifold.variant",
    "gw1.contract.status",
    "gw1.hp.boss.state",
    "gw1.leaf.ally.all.tanks.event",
    "gw1.leaf.ally.buffer.only.event",
    "gw1.local.control.all.tanks.event",
    "gw1.local.control.buffer.only.event",
    "gw1.local.control.standby.top.event",
    "gw1.local.control.top.event",
    "gw1.main.auto.event",
    "heat.pump.control",
    "hp.loop.keep.send",
    "hp.model",
    "pico.cycler.event",
    "pico.cycler.state",
    "primary.pump.control",
    "relay.pin.state",
    "store.flow.relay",
    "top.event",
    "top.state",
    "turn.hp.on.off",
}

# --- KNOWN conformance debt to burn down (should shrink to empty) ---
KNOWN_ENUM_VERSION_DRIFT: set[str] = set()

KNOWN_FORMAT_ISSUES: set[str] = set()


@pytest.fixture(scope="module")
def report() -> conformance.Report:
    if not SEMA_ROOT.exists():
        pytest.skip(f"sibling sema checkout not found at {SEMA_ROOT}")
    return conformance.run(SEMA_ROOT)


def _names(items: list[str]) -> set[str]:
    return {i.split(":")[0].strip() for i in items}


def test_no_type_version_drift(report: conformance.Report) -> None:
    assert report.version_drift == [], (
        "gwsproto type Version literal is not sema latest:\n"
        + "\n".join(report.version_drift)
    )


def test_no_example_reject(report: conformance.Report) -> None:
    assert report.example_reject == [], "\n".join(report.example_reject)


def test_no_dump_drift(report: conformance.Report) -> None:
    assert report.dump_drift == [], "\n".join(report.dump_drift)


def test_no_enum_value_drift(report: conformance.Report) -> None:
    assert report.enum_value_drift == [], "\n".join(report.enum_value_drift)


def test_gwsproto_only_types_match_allowlist(report: conformance.Report) -> None:
    actual = set(report.no_word)
    assert actual == NO_WORD_TYPES, (
        f"newly gwsproto-only (add to sema or allowlist): {sorted(actual - NO_WORD_TYPES)}; "
        f"now in sema (remove from allowlist): {sorted(NO_WORD_TYPES - actual)}"
    )


def test_gwsproto_only_enums_match_allowlist(report: conformance.Report) -> None:
    actual = set(report.enum_no_word)
    assert actual == NO_WORD_ENUMS, (
        f"newly gwsproto-only enums: {sorted(actual - NO_WORD_ENUMS)}; "
        f"now in sema (remove from allowlist): {sorted(NO_WORD_ENUMS - actual)}"
    )


def test_enum_version_drift_only_known(report: conformance.Report) -> None:
    actual = _names(report.enum_version_drift)
    assert actual == KNOWN_ENUM_VERSION_DRIFT, (
        f"new enum version drift: {sorted(actual - KNOWN_ENUM_VERSION_DRIFT)}; "
        f"fixed (remove from KNOWN list): {sorted(KNOWN_ENUM_VERSION_DRIFT - actual)}"
    )


def test_format_issues_only_known(report: conformance.Report) -> None:
    actual = _names(report.format_reject)
    assert actual == KNOWN_FORMAT_ISSUES, (
        f"new format issue: {sorted(actual - KNOWN_FORMAT_ISSUES)}; "
        f"fixed (remove from KNOWN list): {sorted(KNOWN_FORMAT_ISSUES - actual)}"
    )
