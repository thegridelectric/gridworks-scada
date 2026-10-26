"""gwsproto ↔ sema conformance sweep — check every gwsproto type, enum, and
property format against the scada's vendored sema snapshot.

gwsproto types/enums/formats are hand-written twins of sema vocabulary words;
sema is the contract. The scada vendors its own snapshot of every word it
speaks, at the version it speaks (`sema_snapshot/sema`, committed, generated
by `scripts/regen_sema_snapshot.sh` from `sema_seed_request.yaml`). The
snapshot is the oracle: its definitions, its generated classes and its
canonical samples. This module is
both a CLI (human sweep) and the engine behind the pytest conformance tests
(`tests/named_types/test_gwsproto_sema_conformance.py`,
`tests/named_types/test_axiom_coverage.py`).

Per TYPE it reports:
- **no-word** — TypeName not in the snapshot registry: either gwsproto-only
  (no sema word) or a word sema has that the seed does not name;
- **version-drift** — the gwsproto `Version` literal is not the version the
  seed pins (`indexes/seed_request.yaml`; the snapshot's `latest_version`
  for a word the seed does not name);
- **multi-version** — the snapshot holds the word at more than one version.
  A scada speaks exactly one version of each word, so a second version is a
  dependent in the closure bound to another version than the pin; the report
  names each version's users (`indexes/reverse_dependencies.yaml`);
- **no-oracle** — the snapshot has no class at the twin's pinned version, so
  nothing checks its shape (seed that version);
- **shape-drift** — the twin's serialized field names, or its required set,
  differ from the snapshot class's at the pinned version;
- **sample-reject** — the snapshot's canonical sample for the pinned version
  does not decode through the gwsproto class;
- **dump-drift** — the sample decodes but `model_dump(by_alias=True,
  exclude_none=True)` is not byte-identical to the sample (non-canonical
  serialization);
- **no-sample** — nothing to decode (informational).

Per ENUM it reports no-word, version-drift, multi-version, value-drift (the
gwsproto value set is not the snapshot enum's value set) and default-drift
(the gwsproto `default()` is not the snapshot enum's `default`). Per FORMAT it runs the snapshot
`examples` (must accept) and `counterexamples` (must reject) through the
gwsproto validator.

The REVERSE direction walks the snapshot registry: every type and enum in the
scada's closure must have a gwsproto twin. This is
the check that catches a word reaching sema and the closure with no scada
mirror; the forward checks cannot see a word gwsproto never names.

With --cli, each clean re-dump is additionally validated through the sema CLI
in the sibling sema checkout.

Run from this package directory:

    uv run python gwsproto_sema_conformance.py [--snapshot PATH] [--cli] [-v]
"""

import argparse
import functools
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import gwsproto.enums as gwsproto_enums
import gwsproto.named_types as named_types
import yaml
from gwsproto import property_format as pf
from gwsproto.enums.gw_str_enum import SemaEnum
from pydantic import TypeAdapter

PACKAGE_ROOT = Path(__file__).resolve().parent
# The scada's vendored snapshot: the oracle.
DEFAULT_SNAPSHOT = PACKAGE_ROOT / "sema_snapshot" / "sema"
# packages/gridworks-scada-protocol/ -> repo root -> umbrella dir -> sema
# (only for --cli).
DEFAULT_SEMA = PACKAGE_ROOT.parents[2] / "sema"

# sema format name -> gwsproto property_format Annotated type. Formats gwsproto
# does not mirror are reported as format-no-word.
FORMAT_MAP: dict[str, object] = {
    "decimal.digit": pf.DecimalDigit,
    "git.commit": pf.GitCommit,
    "handle.name": pf.HandleName,
    "hex.char": pf.HexChar,
    "hh.mm": pf.HhMm,
    "iana.timezone.str": pf.IanaTimezoneStr,
    "left.right.dot": pf.LeftRightDotStr,
    "market.slot.name": pf.MarketSlotName,
    "non.negative.int": pf.NonNegativeInt,
    "pascal.case": pf.PascalCase,
    "sema.version": pf.SemaVersion,
    "spaceheat.name": pf.SpaceheatName,
    "utc.iso8601.millis": pf.UtcIso8601Millis,
    "utc.iso8601.seconds": pf.UtcIso8601Seconds,
    "utc.milliseconds": pf.UTCMilliseconds,
    "utc.seconds": pf.UTCSeconds,
    "uuid4.str": pf.UUID4Str,
}

# Fields every sema type carries with a default on both sides; excluded from
# the required-set comparison.
IDENTITY_FIELDS = {"TypeName", "Version"}


def snapshot_present(snapshot_root: Path = DEFAULT_SNAPSHOT) -> bool:
    return (snapshot_root / "definitions" / "registry.yaml").exists()


@functools.lru_cache(maxsize=None)
def load_yaml(path: Path) -> dict | None:
    """One parse per file per process; the snapshot is read-only data."""
    return yaml.safe_load(path.read_text()) if path.exists() else None


def seed_pins(snapshot_root: Path) -> dict[str, dict[str, str]]:
    """{"types": {name: version}, "enums": {name: version}} for every word the
    seed pins to exactly one version (`versions: ["NNN"]`)."""
    seed = load_yaml(snapshot_root / "indexes" / "seed_request.yaml") or {}
    out: dict[str, dict[str, str]] = {"types": {}, "enums": {}}
    for category in out:
        for name, opts in (seed.get("initial_targets") or {}).get(category, {}).items():
            versions = (opts or {}).get("versions")
            if isinstance(versions, list) and len(versions) == 1:
                out[category][name] = str(versions[0])
    return out


def multi_version_words(snapshot_root: Path) -> list[str]:
    """Every type and versioned enum the snapshot holds at more than one
    version, each version with the words that bind to it."""
    versions = load_yaml(snapshot_root / "indexes" / "versions.yaml") or {}
    reverse = load_yaml(snapshot_root / "indexes" / "reverse_dependencies.yaml") or {}
    out: list[str] = []
    for category in ("types", "enums"):
        for name, entry in sorted((versions.get(category) or {}).items()):
            held = sorted(entry.get("versions") or {})
            if len(held) < 2:
                continue
            users = (reverse.get(category) or {}).get(name) or {}
            by_version = ", ".join(
                f"{v}<-{sorted((users.get(v) or {}).get('used_by') or [])}" for v in held
            )
            out.append(f"{category[:-1]} {name}: {by_version}")
    return out


def load_definitions(snapshot_root: Path, wanted: dict[str, str]) -> dict:
    """Registry + the wanted schema files (paths relative to the snapshot's
    `definitions/`), parsed. A missing schema file maps to None."""
    defs = snapshot_root / "definitions"
    return {
        "registry": load_yaml(defs / "registry.yaml"),
        "schemas": {key: load_yaml(defs / rel) for key, rel in wanted.items()},
    }


@functools.lru_cache(maxsize=None)
def snapshot_classes(snapshot_root: Path) -> dict[str, dict[str | None, type]]:
    """TypeName -> {Version: generated snapshot class}, current and old."""
    parent = snapshot_root.parent
    if str(parent) not in sys.path:
        sys.path.insert(0, str(parent))
    from sema_snapshot.sema.codec import SemaCodec  # noqa: PLC0415

    codec = SemaCodec()
    out: dict[str, dict[str | None, type]] = {}
    for type_name, cls in codec.registry.items():
        out.setdefault(type_name, {})[cls.version_value()] = cls
    for type_name, by_version in codec.old_versions.items():
        for version, cls in by_version.items():
            out.setdefault(type_name, {})[version] = cls
    return out


def gwsproto_classes() -> dict[str, tuple[type, str | None]]:
    """TypeName -> (class, declared Version or None) for every exported named type."""
    out: dict[str, tuple[type, str | None]] = {}
    for name in named_types.__all__:
        cls = getattr(named_types, name)
        fields = getattr(cls, "model_fields", None)
        if not fields:
            continue
        # snake-field types (alias_generator=snake_to_camel) declare
        # `type_name` / `version`; the wire names are still TypeName / Version.
        type_key = "TypeName" if "TypeName" in fields else "type_name"
        version_key = "Version" if "Version" in fields else "version"
        if type_key not in fields:
            continue
        type_name = fields[type_key].default
        version = fields[version_key].default if version_key in fields else None
        out[type_name] = (cls, version)
    return out


def gwsproto_enum_classes() -> dict[str, type]:
    """enum_name -> SemaEnum subclass for every gwsproto sema enum."""
    out: dict[str, type] = {}
    for name in dir(gwsproto_enums):
        obj = getattr(gwsproto_enums, name)
        if not (
            isinstance(obj, type) and issubclass(obj, SemaEnum) and obj is not SemaEnum
        ):
            continue
        try:
            enum_name = obj.enum_name()
        except (NotImplementedError, AttributeError):
            continue
        out[enum_name] = obj
    return out


def wire_fields(cls: type) -> tuple[set[str], set[str]]:
    """(serialized field names, required serialized field names) of a pydantic
    model, by alias where one is set."""
    names: set[str] = set()
    required: set[str] = set()
    for name, info in cls.model_fields.items():
        wire = info.alias or name
        names.add(wire)
        if info.is_required():
            required.add(wire)
    return names, required


def sema_cli_validate(sema_root: Path, payload: dict) -> str | None:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
        path = f.name
    result = subprocess.run(
        ["uv", "run", "sema", "validate", path],
        cwd=sema_root,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return None
    return (result.stdout + result.stderr).strip().splitlines()[-1][:200]


@dataclass(frozen=True)
class ShapeDrift:
    """How a twin's wire shape differs from the snapshot class at the same
    version. Each list is sorted serialized field names; an empty drift is
    never recorded."""

    gwsproto_only: tuple[str, ...] = ()
    snapshot_only: tuple[str, ...] = ()
    required_only_in_gwsproto: tuple[str, ...] = ()
    required_only_in_snapshot: tuple[str, ...] = ()

    def __str__(self) -> str:
        return (
            f"gwsproto-only={list(self.gwsproto_only)} "
            f"snapshot-only={list(self.snapshot_only)} "
            f"required-only-in-gwsproto={list(self.required_only_in_gwsproto)} "
            f"required-only-in-snapshot={list(self.required_only_in_snapshot)}"
        )


@dataclass
class Report:
    snapshot: str = ""
    n_snapshot_types: int = 0
    n_gwsproto_types: int = 0
    # types
    no_word: list[str] = field(default_factory=list)
    version_drift: list[str] = field(default_factory=list)
    # snapshot words held at more than one version (types and enums)
    multi_version: list[str] = field(default_factory=list)
    no_oracle: list[str] = field(default_factory=list)
    # "type/version" -> the exact drift: the four sorted field lists.
    shape_drift: dict[str, "ShapeDrift"] = field(default_factory=dict)
    sample_reject: list[str] = field(default_factory=list)
    dump_drift: list[str] = field(default_factory=list)
    cli_reject: list[str] = field(default_factory=list)
    no_sample: list[str] = field(default_factory=list)
    # enums
    enum_no_word: list[str] = field(default_factory=list)
    enum_version_drift: list[str] = field(default_factory=list)
    enum_value_drift: list[str] = field(default_factory=list)
    enum_default_drift: list[str] = field(default_factory=list)
    # formats
    format_reject: list[str] = field(default_factory=list)
    format_no_word: list[str] = field(default_factory=list)
    # reverse: snapshot words with no gwsproto twin
    snapshot_unmirrored_types: list[str] = field(default_factory=list)
    snapshot_unmirrored_enums: list[str] = field(default_factory=list)


def _enum_values(schema: dict | None) -> set[str] | None:
    if not schema:
        return None
    vals = schema.get("enum")
    return set(vals) if vals is not None else None


def check_reverse(r: Report, registry: dict) -> None:
    """Every type and enum in the snapshot has a gwsproto twin. A miss means a
    word the scada speaks, or one its closure reaches, has no scada mirror.
    Version drift on a word that has a twin is the forward check's."""
    classes = gwsproto_classes()
    enums = gwsproto_enum_classes()
    for type_name, entry in sorted(registry.get("types", {}).items()):
        if type_name not in classes:
            r.snapshot_unmirrored_types.append(
                f"{type_name}/{entry.get('latest_version')}"
            )
    for enum_name, entry in sorted(registry.get("enums", {}).items()):
        if enum_name not in enums:
            latest = entry.get("latest_version")
            r.snapshot_unmirrored_enums.append(
                f"{enum_name}/{latest}"
                if entry.get("enum_type") == "versioned"
                else enum_name
            )


def run(  # noqa: C901
    snapshot_root: Path = DEFAULT_SNAPSHOT,
    *,
    cli: bool = False,
    sema_root: Path = DEFAULT_SEMA,
) -> Report:
    r = Report(snapshot=str(snapshot_root))

    classes = gwsproto_classes()
    enums = gwsproto_enum_classes()
    oracle = snapshot_classes(snapshot_root)

    registry = load_definitions(snapshot_root, {})["registry"]
    snap_types = registry["types"]
    snap_enums = registry.get("enums", {})
    r.n_snapshot_types = len(snap_types)
    r.n_gwsproto_types = len(classes)
    pins = seed_pins(snapshot_root)
    r.multi_version = multi_version_words(snapshot_root)

    # ---- types ----
    samples_dir = snapshot_root / "samples"
    for type_name in sorted(classes):
        cls, version = classes[type_name]
        entry = snap_types.get(type_name)
        if entry is None:
            r.no_word.append(type_name)
            continue
        pinned = pins["types"].get(type_name, entry.get("latest_version"))
        if version != pinned:
            r.version_drift.append(
                f"{type_name}: gwsproto {version} vs snapshot {pinned}"
            )
        snap_cls = oracle.get(type_name, {}).get(version)
        if snap_cls is None:
            r.no_oracle.append(f"{type_name}/{version}")
        else:
            gws_names, gws_required = wire_fields(cls)
            snap_names, snap_required = wire_fields(snap_cls)
            gws_required -= IDENTITY_FIELDS
            snap_required -= IDENTITY_FIELDS
            if gws_names != snap_names or gws_required != snap_required:
                r.shape_drift[f"{type_name}/{version}"] = ShapeDrift(
                    tuple(sorted(gws_names - snap_names)),
                    tuple(sorted(snap_names - gws_names)),
                    tuple(sorted(gws_required - snap_required)),
                    tuple(sorted(snap_required - gws_required)),
                )
        sample = samples_dir / (
            f"{type_name}.{version}.json" if version else f"{type_name}.json"
        )
        if not sample.exists():
            r.no_sample.append(f"{type_name}/{version}")
            continue
        doc = json.loads(sample.read_text())
        try:
            decoded = cls.model_validate(doc)
        except Exception as exc:  # noqa: BLE001
            r.sample_reject.append(f"{type_name}/{version}: {str(exc)[:140]}")
            continue
        dump = decoded.model_dump(by_alias=True, exclude_none=True, mode="json")
        if dump != doc:
            gone = sorted(set(doc) - set(dump))
            added = sorted(set(dump) - set(doc))
            changed = sorted(k for k in set(doc) & set(dump) if doc[k] != dump[k])
            r.dump_drift.append(
                f"{type_name}/{version}: missing={gone} extra={added} changed={changed}"
            )
            continue
        if cli:
            err = sema_cli_validate(sema_root, dump)
            if err:
                r.cli_reject.append(f"{type_name}/{version}: {err}")

    # ---- enums ----
    enum_wanted: dict[str, str] = {}
    for enum_name, ecls in enums.items():
        entry = snap_enums.get(enum_name)
        if entry is None:
            continue
        if entry.get("enum_type") == "versioned":
            try:
                version = ecls.enum_version()
            except (NotImplementedError, AttributeError):
                version = None
            enum_wanted[f"enum::{enum_name}"] = f"enums/{enum_name}/{version}.yaml"
        else:
            enum_wanted[f"enum::{enum_name}"] = f"enums/{enum_name}.yaml"
    fmt_wanted = {f"fmt::{fmt}": f"formats/{fmt}.yaml" for fmt in FORMAT_MAP}
    schemas = load_definitions(snapshot_root, {**enum_wanted, **fmt_wanted})["schemas"]

    for enum_name in sorted(enums):
        ecls = enums[enum_name]
        entry = snap_enums.get(enum_name)
        if entry is None:
            r.enum_no_word.append(enum_name)
            continue
        try:
            version = ecls.enum_version()
        except (NotImplementedError, AttributeError):
            version = None
        if entry.get("enum_type") == "versioned":
            pinned = pins["enums"].get(enum_name, entry.get("latest_version"))
            if version != pinned:
                r.enum_version_drift.append(
                    f"{enum_name}: gwsproto {version} vs snapshot {pinned}"
                )
        schema = schemas.get(f"enum::{enum_name}")
        snap_vals = _enum_values(schema)
        gws_vals = set(ecls.values())
        if snap_vals is not None and gws_vals != snap_vals:
            r.enum_value_drift.append(
                f"{enum_name}: gwsproto-only={sorted(gws_vals - snap_vals)} "
                f"snapshot-only={sorted(snap_vals - gws_vals)}"
            )
        snap_default = schema.get("default") if schema else None
        if snap_default is not None:
            gws_default = getattr(ecls.default(), "value", ecls.default())
            if gws_default != snap_default:
                r.enum_default_drift.append(
                    f"{enum_name}: gwsproto default {gws_default!r} "
                    f"vs snapshot {snap_default!r}"
                )

    # ---- formats ----
    for fmt, gws_type in FORMAT_MAP.items():
        schema = schemas.get(f"fmt::{fmt}")
        if schema is None:
            r.format_no_word.append(fmt)
            continue
        adapter = TypeAdapter(gws_type)
        for ex in schema.get("examples") or []:
            try:
                adapter.validate_python(ex)
            except Exception as exc:  # noqa: BLE001
                r.format_reject.append(
                    f"{fmt}: rejects valid example {ex!r}: {str(exc)[:80]}"
                )
        for ce in schema.get("counterexamples") or []:
            try:
                adapter.validate_python(ce)
                r.format_reject.append(f"{fmt}: ACCEPTS counterexample {ce!r}")
            except Exception:  # noqa: BLE001, S110
                pass

    check_reverse(r, registry)
    return r


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--sema", type=Path, default=DEFAULT_SEMA, help="for --cli")
    parser.add_argument("--cli", action="store_true", help="also run `sema validate`")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    if not snapshot_present(args.snapshot):
        print(
            f"snapshot missing at {args.snapshot}; run scripts/regen_sema_snapshot.sh",
            file=sys.stderr,
        )
        return 2
    r = run(args.snapshot.resolve(), cli=args.cli, sema_root=args.sema.resolve())
    print(f"snapshot: {r.snapshot} — {r.n_snapshot_types} types")
    print(f"gwsproto: {r.n_gwsproto_types} named types\n")

    def section(title: str, items: list[str]) -> None:
        if items:
            print(f"\n== {title} ({len(items)}) ==")
            for item in items:
                print(f"  {item}")

    section("TYPE — no snapshot word", r.no_word)
    section("TYPE — version drift", r.version_drift)
    section("SNAPSHOT — word held at more than one version", r.multi_version)
    section("TYPE — no snapshot class at pinned version", r.no_oracle)
    section("TYPE — shape drift", [f"{k}: {v}" for k, v in r.shape_drift.items()])
    section("TYPE — sample reject", r.sample_reject)
    section("TYPE — dump drift", r.dump_drift)
    section("TYPE — sema CLI reject", r.cli_reject)
    if args.verbose:
        section("TYPE — no sample", r.no_sample)
    section("ENUM — no snapshot word", r.enum_no_word)
    section("ENUM — version drift", r.enum_version_drift)
    section("ENUM — value drift", r.enum_value_drift)
    section("ENUM — default drift", r.enum_default_drift)
    section("FORMAT — reject", r.format_reject)
    section("FORMAT — no snapshot word (unmirrored)", r.format_no_word)
    section("SNAPSHOT — type with no gwsproto twin", r.snapshot_unmirrored_types)
    section("SNAPSHOT — enum with no gwsproto twin", r.snapshot_unmirrored_enums)

    failures = (
        r.version_drift
        + r.multi_version
        + r.no_oracle
        + list(r.shape_drift)
        + r.sample_reject
        + r.dump_drift
        + r.cli_reject
        + r.enum_version_drift
        + r.enum_value_drift
        + r.enum_default_drift
        + r.format_reject
        + r.snapshot_unmirrored_types
        + r.snapshot_unmirrored_enums
    )
    print(
        f"\n{len(failures)} conformance failure(s); {len(r.no_word)} type(s) without a word."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
