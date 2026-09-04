"""gwsproto ↔ sema conformance sweep — check every gwsproto type, enum, and
property format against the sema contract.

gwsproto types/enums/formats are hand-written twins of sema vocabulary words;
sema is the contract (scada protocol: validate against the canonical runtime).
This module is both a CLI (human sweep) and the engine behind the pytest
conformance test (`tests/named_types/test_gwsproto_sema_conformance.py`).

Per TYPE it reports:
- **no-word** — TypeName not in the sema registry (gwsproto-only, e.g. types
  not yet added to sema);
- **version-drift** — the gwsproto `Version` literal is not the sema
  `latest_version`;
- **example-reject** — the sema example for the pinned version does not decode
  through the gwsproto class (gwsproto rejects canonical sema data);
- **dump-drift** — the example decodes but `model_dump(by_alias=True,
  exclude_none=True)` != the example document (non-canonical serialization);
- **no-example** — nothing to decode (informational).

Per ENUM it reports no-word, version-drift, and value-drift (the gwsproto value
set is not the sema enum's value set). Per FORMAT it runs the sema `examples`
(must accept) and `counterexamples` (must reject) through the gwsproto validator.

The REVERSE direction runs against `sema_closure/registry.yaml` beside this
file: a vendored copy of the tlayouts snapshot registry, the dependency closure
of the layout words — every word a layout artifact can carry. Each type and
enum there must have a gwsproto twin at the closure's version. This is the
check that catches a word landing in sema and the layout closure with no scada
mirror; the forward checks above cannot see a word gwsproto never names. The
copy is refreshed whenever tlayouts regenerates its snapshot.

Reads the sibling sema checkout's definitions directly (report which branch!).
With --cli, each clean re-dump is additionally validated through the sema CLI.

Run from this package directory:

    uv run python gwsproto_sema_conformance.py [--sema PATH] [--cli] [-v]
"""

import argparse
import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import gwsproto.enums as gwsproto_enums
import gwsproto.named_types as named_types
from gwsproto import property_format as pf
from gwsproto.enums.gw_str_enum import SemaEnum
from pydantic import TypeAdapter

# packages/gridworks-scada-protocol/ -> repo root -> umbrella dir -> sema
DEFAULT_SEMA = Path(__file__).resolve().parents[3] / "sema"
# Vendored copy of the tlayouts snapshot registry: the layout-word closure.
DEFAULT_CLOSURE_REGISTRY = Path(__file__).resolve().parent / "sema_closure" / "registry.yaml"

# sema format name -> gwsproto property_format Annotated type. Formats gwsproto
# does not mirror are listed in UNMIRRORED_FORMATS below (checked-in record).
FORMAT_MAP: dict[str, object] = {
    "handle.name": pf.HandleName,
    "hex.char": pf.HexChar,
    "hh.mm": pf.HhMm,
    "left.right.dot": pf.LeftRightDotStr,
    "market.slot.name": pf.MarketSlotName,
    "non.negative.int": pf.NonNegativeInt,
    "pascal.case": pf.PascalCase,
    "spaceheat.name": pf.SpaceheatName,
    "utc.iso8601.millis": pf.UtcIso8601Millis,
    "utc.iso8601.seconds": pf.UtcIso8601Seconds,
    "utc.milliseconds": pf.UTCMilliseconds,
    "utc.seconds": pf.UTCSeconds,
    "uuid4.str": pf.UUID4Str,
}

# The scada venv carries no YAML library; the sema checkout's uv env does. One
# subprocess converts the registry + every needed schema file to JSON.
_YAML_TO_JSON = """
import json, sys, yaml
from pathlib import Path
request = json.load(sys.stdin)
wanted = request["schemas"]
out = {"registry": yaml.safe_load(Path(request["registry"]).read_text()), "schemas": {}}
for key, rel in wanted.items():
    p = Path(rel)
    out["schemas"][key] = yaml.safe_load(p.read_text()) if p.exists() else None
json.dump(out, sys.stdout)
"""


def load_sema(
    sema_root: Path, wanted: dict[str, str], registry: Path | None = None
) -> dict:
    """Registry + schema files as JSON. `registry` defaults to the sema
    checkout's own; pass the vendored closure registry to read it (the
    subprocess still runs in the sema env, which has the YAML library)."""
    registry_path = registry or sema_root / "definitions" / "registry.yaml"
    result = subprocess.run(
        ["uv", "run", "python", "-c", _YAML_TO_JSON],
        cwd=sema_root,
        input=json.dumps({"registry": str(registry_path), "schemas": wanted}),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"sema definitions load failed: {result.stderr[-400:]}")
    return json.loads(result.stdout)


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
        cls = getattr(gwsproto_enums, name)
        if isinstance(cls, type) and issubclass(cls, SemaEnum) and cls is not SemaEnum:
            try:
                out[cls.enum_name()] = cls
            except NotImplementedError:
                continue
    return out


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


@dataclass
class Report:
    branch: str = ""
    n_sema_types: int = 0
    n_gwsproto_types: int = 0
    # types
    no_word: list[str] = field(default_factory=list)
    version_drift: list[str] = field(default_factory=list)
    example_reject: list[str] = field(default_factory=list)
    dump_drift: list[str] = field(default_factory=list)
    cli_reject: list[str] = field(default_factory=list)
    no_example: list[str] = field(default_factory=list)
    # enums
    enum_no_word: list[str] = field(default_factory=list)
    enum_version_drift: list[str] = field(default_factory=list)
    enum_value_drift: list[str] = field(default_factory=list)
    # formats
    format_reject: list[str] = field(default_factory=list)
    format_no_word: list[str] = field(default_factory=list)
    # reverse: layout-closure words with no gwsproto twin / off-version twin
    closure_registry: str = ""
    n_snapshot_types: int = 0
    snapshot_unmirrored_types: list[str] = field(default_factory=list)
    snapshot_unmirrored_enums: list[str] = field(default_factory=list)
    snapshot_version_drift: list[str] = field(default_factory=list)


def _enum_values(schema: dict | None) -> set[str] | None:
    if not schema:
        return None
    vals = schema.get("enum")
    return set(vals) if vals is not None else None


def check_snapshot(r: Report, sema_root: Path, registry_path: Path) -> None:
    """Reverse direction: every type and enum in the vendored layout-closure
    registry has a gwsproto twin pinned at the closure's latest version. A
    miss means a layout artifact can carry a word the scada cannot decode."""
    if not registry_path.exists():
        return
    r.closure_registry = str(registry_path)
    snapshot = load_sema(sema_root, {}, registry=registry_path)["registry"]
    classes = gwsproto_classes()
    enums = gwsproto_enum_classes()
    snapshot_types = snapshot.get("types", {})
    r.n_snapshot_types = len(snapshot_types)
    for type_name in sorted(snapshot_types):
        latest = snapshot_types[type_name].get("latest_version")
        if type_name not in classes:
            r.snapshot_unmirrored_types.append(f"{type_name}/{latest}")
            continue
        version = classes[type_name][1]
        if version != latest:
            r.snapshot_version_drift.append(
                f"{type_name}: gwsproto {version} vs snapshot {latest}"
            )
    for enum_name, entry in sorted(snapshot.get("enums", {}).items()):
        versioned = entry.get("enum_type") == "versioned"
        latest = entry.get("latest_version") if versioned else None
        if enum_name not in enums:
            r.snapshot_unmirrored_enums.append(
                f"{enum_name}/{latest}" if versioned else enum_name
            )
            continue
        if not versioned:
            continue
        try:
            version = enums[enum_name].enum_version()
        except (NotImplementedError, AttributeError):
            version = None
        if version != latest:
            r.snapshot_version_drift.append(
                f"{enum_name}: gwsproto {version} vs snapshot {latest}"
            )


def run(
    sema_root: Path, *, cli: bool = False, closure_registry: Path | None = None
) -> Report:  # noqa: C901
    r = Report()
    r.branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=sema_root,
        capture_output=True, text=True,
    ).stdout.strip()

    classes = gwsproto_classes()
    enums = gwsproto_enum_classes()

    # One batched YAML->JSON load: type schemas + enum schemas.
    wanted: dict[str, str] = {}
    for type_name, (_, version) in classes.items():
        wanted[f"type::{type_name}"] = (
            f"definitions/types/{type_name}/{version}.yaml"
            if version is not None
            else f"definitions/types/{type_name}.yaml"
        )
    for enum_name in enums:
        wanted[f"enum::{enum_name}"] = f"definitions/enums/{enum_name}.yaml"  # literal
    # versioned enums live under a version dir; add latest-version candidates too
    # (resolved after we read the registry — so add a broad set here).
    for fmt in FORMAT_MAP:
        wanted[f"fmt::{fmt}"] = f"definitions/formats/{fmt}.yaml"

    loaded = load_sema(sema_root, wanted)
    registry = loaded["registry"]
    sema_types = registry["types"]
    sema_enums = registry.get("enums", {})
    schemas = loaded["schemas"]
    r.n_sema_types = len(sema_types)
    r.n_gwsproto_types = len(classes)

    # ---- types ----
    for type_name in sorted(classes):
        cls, version = classes[type_name]
        entry = sema_types.get(type_name)
        if entry is None:
            r.no_word.append(type_name)
            continue
        latest = entry.get("latest_version")
        if version != latest:
            r.version_drift.append(f"{type_name}: gwsproto {version} vs sema {latest}")
        schema = schemas.get(f"type::{type_name}")
        examples = (schema or {}).get("examples") or []
        if not examples:
            r.no_example.append(f"{type_name}/{version}")
            continue
        for i, ex in enumerate(examples):
            doc = json.loads(ex)
            try:
                decoded = cls.model_validate(doc)
            except Exception as exc:  # noqa: BLE001
                r.example_reject.append(f"{type_name}/{version}[{i}]: {str(exc)[:140]}")
                continue
            dump = decoded.model_dump(by_alias=True, exclude_none=True, mode="json")
            if dump != doc:
                gone = sorted(set(doc) - set(dump))
                added = sorted(set(dump) - set(doc))
                changed = sorted(k for k in set(doc) & set(dump) if doc[k] != dump[k])
                r.dump_drift.append(
                    f"{type_name}/{version}[{i}]: missing={gone} extra={added} changed={changed}"
                )
                continue
            if cli:
                err = sema_cli_validate(sema_root, dump)
                if err:
                    r.cli_reject.append(f"{type_name}/{version}[{i}]: {err}")

    # ---- enums ----
    # Second batched load for versioned-enum schemas at their gwsproto version.
    enum_wanted: dict[str, str] = {}
    for enum_name, ecls in enums.items():
        entry = sema_enums.get(enum_name)
        version = None
        try:
            version = ecls.enum_version()
        except (NotImplementedError, AttributeError):
            version = None
        if entry and (entry.get("enum_type") == "versioned") and version:
            enum_wanted[f"enum::{enum_name}"] = f"definitions/enums/{enum_name}/{version}.yaml"
    if enum_wanted:
        more = load_sema(sema_root, enum_wanted)["schemas"]
        schemas.update(more)

    for enum_name in sorted(enums):
        ecls = enums[enum_name]
        entry = sema_enums.get(enum_name)
        if entry is None:
            r.enum_no_word.append(enum_name)
            continue
        try:
            version = ecls.enum_version()
        except (NotImplementedError, AttributeError):
            version = None
        if entry.get("enum_type") == "versioned":
            latest = entry.get("latest_version")
            if version != latest:
                r.enum_version_drift.append(
                    f"{enum_name}: gwsproto {version} vs sema {latest}"
                )
        sema_vals = _enum_values(schemas.get(f"enum::{enum_name}"))
        gws_vals = set(ecls.values())
        if sema_vals is not None and gws_vals != sema_vals:
            r.enum_value_drift.append(
                f"{enum_name}: gwsproto-only={sorted(gws_vals - sema_vals)} "
                f"sema-only={sorted(sema_vals - gws_vals)}"
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
                r.format_reject.append(f"{fmt}: rejects valid example {ex!r}: {str(exc)[:80]}")
        for ce in schema.get("counterexamples") or []:
            try:
                adapter.validate_python(ce)
                r.format_reject.append(f"{fmt}: ACCEPTS counterexample {ce!r}")
            except Exception:  # noqa: BLE001, S110
                pass

    check_snapshot(r, sema_root, closure_registry or DEFAULT_CLOSURE_REGISTRY)
    return r


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sema", type=Path, default=DEFAULT_SEMA)
    parser.add_argument("--cli", action="store_true", help="also run `sema validate`")
    parser.add_argument(
        "--closure-registry",
        type=Path,
        default=DEFAULT_CLOSURE_REGISTRY,
        help="vendored layout-closure registry (reverse check)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    r = run(
        args.sema.resolve(), cli=args.cli, closure_registry=args.closure_registry.resolve()
    )
    print(f"sema: {args.sema} (branch: {r.branch}) — {r.n_sema_types} registered types")
    print(f"gwsproto: {r.n_gwsproto_types} named types")
    if r.closure_registry:
        print(f"layout closure: {r.closure_registry} — {r.n_snapshot_types} types\n")
    else:
        print(f"layout closure: {args.closure_registry} missing (reverse check skipped)\n")

    def section(title: str, items: list[str]) -> None:
        if items:
            print(f"\n== {title} ({len(items)}) ==")
            for item in items:
                print(f"  {item}")

    section("TYPE — no sema word", r.no_word)
    section("TYPE — version drift", r.version_drift)
    section("TYPE — example reject", r.example_reject)
    section("TYPE — dump drift", r.dump_drift)
    section("TYPE — sema CLI reject", r.cli_reject)
    section("ENUM — no sema word", r.enum_no_word)
    section("ENUM — version drift", r.enum_version_drift)
    section("ENUM — value drift", r.enum_value_drift)
    section("FORMAT — reject", r.format_reject)
    section("FORMAT — no sema word (unmirrored)", r.format_no_word)
    section("CLOSURE — type with no gwsproto twin", r.snapshot_unmirrored_types)
    section("CLOSURE — enum with no gwsproto twin", r.snapshot_unmirrored_enums)
    section("CLOSURE — version drift", r.snapshot_version_drift)

    failures = (
        r.version_drift + r.example_reject + r.dump_drift + r.cli_reject
        + r.enum_version_drift + r.enum_value_drift + r.format_reject
        + r.snapshot_unmirrored_types + r.snapshot_unmirrored_enums
        + r.snapshot_version_drift
    )
    print(f"\n{len(failures)} conformance failure(s); {len(r.no_word)} type(s) without a word.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
