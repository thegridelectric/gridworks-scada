"""Round-trip harness for this Sema snapshot.

Walks ``samples/`` (one canonical JSON instance per type version) and proves
the emitted runtime can decode its own types: for each sample,

  decode (at its own version) -> re-encode -> deep-equal the sample bytes,

and, for a superseded version, additionally

  decode (old) -> upgrade to latest -> re-encode (must succeed).

A sample's bytes are exactly what the runtime emits over the wire (the build
wrote them via ``from_dict -> to_dict``), so a stable round-trip means the
restricted vocabulary in this snapshot is closed and self-consistent. This is
the check that catches a vocabulary word missing *only* from the restricted
snapshot (the ``atn.bid`` class of bug).

Structural validation is the generated pydantic model itself: ``from_dict``
runs full model validation, so a sample that decodes has satisfied the schema
the model was generated from. No external JSON-Schema validator is required.

Run standalone:  ``python -m sema_snapshot.sema.roundtrip``
Or import and call ``run_roundtrip()`` from your own test.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from sema_snapshot.sema.base import UpgradeRequiresContext
from sema_snapshot.sema.codec import default_codec

SAMPLES_DIR = Path(__file__).resolve().parent / "samples"


@dataclass(frozen=True)
class RoundTripFailure:
    sample: str
    reason: str


def _decode_at_own_version(data: dict):
    """Decode strictly at the sample's declared version (no auto-upgrade)."""
    return default_codec.from_dict(data, mode="strict", auto_upgrade=False)


def check_sample(path: Path) -> RoundTripFailure | None:
    raw = path.read_text()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return RoundTripFailure(path.name, f"sample is not valid JSON: {exc}")

    type_name = data.get("TypeName")
    version = data.get("Version")

    try:
        instance = _decode_at_own_version(data)
    except Exception as exc:  # noqa: BLE001 - report any decode failure verbatim
        return RoundTripFailure(path.name, f"decode failed: {exc}")

    reencoded = instance.to_dict()
    if reencoded != data:
        return RoundTripFailure(
            path.name,
            "re-encoded form differs from the sample (not a stable canonical "
            f"round-trip). sample={data!r} reencoded={reencoded!r}",
        )

    # Superseded version: exercise the upgrade chain to latest. A version whose
    # upgrade legitimately needs out-of-band context refuses with
    # UpgradeRequiresContext — that is an expected outcome, not a failure (the
    # sample still proved decode-at-own-version above).
    current_cls = default_codec.registry.get(type_name)
    if current_cls is not None and version != current_cls.version_value():
        try:
            upgraded = default_codec.from_dict(data, mode="strict", auto_upgrade=True)
            upgraded.to_dict()
        except UpgradeRequiresContext:
            pass
        except Exception as exc:  # noqa: BLE001
            return RoundTripFailure(
                path.name, f"upgrade decode-old -> latest failed: {exc}"
            )

    return None


def run_roundtrip(samples_dir: Path | None = None) -> list[RoundTripFailure]:
    samples_dir = samples_dir or SAMPLES_DIR
    if not samples_dir.exists():
        return []
    failures: list[RoundTripFailure] = []
    for path in sorted(samples_dir.glob("*.json")):
        failure = check_sample(path)
        if failure is not None:
            failures.append(failure)
    return failures


def main() -> int:
    failures = run_roundtrip()
    sample_count = (
        len(sorted(SAMPLES_DIR.glob("*.json"))) if SAMPLES_DIR.exists() else 0
    )
    if failures:
        print(f"Round-trip FAILED for {len(failures)}/{sample_count} sample(s):")
        for failure in failures:
            print(f"  - {failure.sample}: {failure.reason}")
        return 1
    print(f"Round-trip OK: {sample_count} sample(s) decode and re-encode cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
