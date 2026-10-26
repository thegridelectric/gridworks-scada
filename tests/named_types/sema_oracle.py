"""The scada's vendored sema snapshot as the oracle for hand-written gwsproto twins.

Every instance a named-types test builds goes through here: what the twin
accepts the snapshot's generated class must accept and re-encode identically,
and what the twin refuses the snapshot must refuse for the same stated reason.
The snapshot's axiom bodies are the sema runtime's own, so this is `sema
validate` as a local test against the vendored copy.

The snapshot is committed (`scripts/regen_sema_snapshot.sh` regenerates it).
"""

import functools
import re
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

_PKG = Path(__file__).resolve().parents[2] / "packages" / "gridworks-scada-protocol"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

import gwsproto_sema_conformance as conformance  # noqa: E402

SNAPSHOT = conformance.DEFAULT_SNAPSHOT


@functools.lru_cache(maxsize=1)
def codec():
    assert conformance.snapshot_present(SNAPSHOT), (
        f"sema snapshot missing at {SNAPSHOT} (scripts/regen_sema_snapshot.sh)"
    )
    conformance.snapshot_classes(SNAPSHOT)
    from sema_snapshot.sema.codec import SemaCodec  # noqa: PLC0415

    return SemaCodec()


def snapshot_errors() -> tuple[type[Exception], ...]:
    """What the snapshot raises on a refused payload: its own SemaError wraps
    pydantic's ValidationError; a bare ValueError comes from the codec."""
    from sema_snapshot.sema.base import SemaError  # noqa: PLC0415

    return (SemaError, ValueError)


def has_word(snapshot, type_name: str) -> bool:
    """A twin with no sema word (the conformance sweep's NO_WORD allowlist)
    has no snapshot leg; only the twin's own checks apply."""
    return type_name in snapshot.registry


def axiom_names(payload: dict) -> dict[int, list[str]]:
    """Axiom number -> [name] from the snapshot definition of the payload's
    type and version; a snapshot message may name an axiom without numbering it."""
    type_name, version = payload["TypeName"], payload.get("Version")
    rel = f"types/{type_name}/{version}.yaml" if version else f"types/{type_name}.yaml"
    schema = conformance.load_definitions(SNAPSHOT, {"t": rel})["schemas"]["t"] or {}
    axioms = (schema.get("x-gridworks") or {}).get("axioms") or []
    return {int(a["number"]): [a["name"]] for a in axioms if "name" in a}


def assert_conforms(instance: BaseModel) -> None:
    """The snapshot accepts the twin's wire form and re-encodes it identically."""
    wire = instance.model_dump(by_alias=True, exclude_none=True, mode="json")
    snapshot = codec()
    if not has_word(snapshot, wire["TypeName"]):
        return
    decoded = snapshot.from_dict(wire, auto_upgrade=False)
    assert decoded.to_dict() == wire, (
        f"snapshot re-encodes {wire['TypeName']} differently: {decoded.to_dict()} != {wire}"
    )


def assert_refused(cls: type[BaseModel], payload: dict, match: str | None = None) -> None:
    """Both the twin and the snapshot refuse the payload. With `match`, the
    twin's message matches it, and the snapshot's refusal names the same
    axiom: by number (`Axiom n`) or by the name in parentheses, whichever
    `match` states. The two runtimes word their messages differently, so the
    axiom identity is what is compared, not the text."""
    with pytest.raises(ValueError, match=match):
        cls.model_validate(payload)
    snapshot = codec()
    if not has_word(snapshot, payload.get("TypeName", "")):
        return
    with pytest.raises(snapshot_errors()) as snap:
        snapshot.from_dict(payload, auto_upgrade=False)
    if match is None:
        return
    said = str(snap.value)
    number = re.search(r"Axiom (\d+)", match)
    name = re.search(r"\\\((\w+)\\\)", match)
    wants = []
    if number:
        wants.append(rf"Axiom {number.group(1)}\b")
        wants.extend(re.escape(n) for n in axiom_names(payload)[int(number.group(1))])
    if name:
        wants.append(re.escape(name.group(1)))
    if wants and not any(re.search(w, said) for w in wants):
        raise AssertionError(
            f"twin refused on {match!r}; snapshot refused on another axiom: {said[:300]}"
        )
