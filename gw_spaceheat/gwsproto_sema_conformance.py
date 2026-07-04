"""gwsproto ↔ sema conformance sweep — check every gwsproto named type against sema.

gwsproto types are hand-written twins of sema vocabulary words; sema is the
contract (scada protocol: validate against the canonical runtime). This sweep
walks every class in `gwsproto.named_types` and reports, per type:

- **no-word** — gwsproto types whose TypeName is not in the sema registry (the
  exceptions to call out and/or add to sema);
- **version-drift** — the gwsproto `Version` literal is not the sema
  `latest_version` (catch-up candidates; the sema-side version may also be
  draft or unknown);
- **example-reject** — the sema example for the gwsproto-declared version does
  not decode through the gwsproto class (gwsproto rejects canonical sema data);
- **dump-drift** — the example decodes but `model_dump(by_alias=True,
  exclude_none=True)` is not equal to the example document (gwsproto emits
  non-canonical serialization: renamed/extra/defaulted fields, coerced values);
- **no-example** — nothing to decode (informational; latest versions MAY omit
  examples).

Reads the sibling sema checkout's definitions directly (report which branch!).
With --cli, each clean re-dump is additionally validated through the sema CLI
(`uv run sema validate`, run in the sema repo) — slower, belt-and-suspenders.

    venv/bin/python gwsproto_sema_conformance.py [--sema PATH] [--cli] [-v]
"""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import gwsproto.named_types as named_types

DEFAULT_SEMA = Path(__file__).resolve().parent.parent.parent / "sema"

# The scada venv carries no YAML library; the sema checkout's uv env does. One
# subprocess converts the registry + every needed schema file to JSON.
_YAML_TO_JSON = """
import json, sys, yaml
from pathlib import Path
wanted = json.load(sys.stdin)
out = {"registry": yaml.safe_load(Path("definitions/registry.yaml").read_text()), "schemas": {}}
for key, rel in wanted.items():
    p = Path(rel)
    out["schemas"][key] = yaml.safe_load(p.read_text()) if p.exists() else None
json.dump(out, sys.stdout)
"""


def load_sema_definitions(sema_root: Path, wanted: dict[str, str]) -> dict:
    result = subprocess.run(
        ["uv", "run", "python", "-c", _YAML_TO_JSON],
        cwd=sema_root,
        input=json.dumps(wanted),
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
        if not fields or "TypeName" not in fields:
            continue
        type_name = fields["TypeName"].default
        version = fields["Version"].default if "Version" in fields else None
        out[type_name] = (cls, version)
    return out


def sema_cli_validate(sema_root: Path, payload: dict) -> str | None:
    """Run `uv run sema validate` on the payload; None if OK, else the error tail."""
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sema", type=Path, default=DEFAULT_SEMA)
    parser.add_argument(
        "--cli", action="store_true", help="also run `sema validate` per re-dump"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="show per-type OK lines"
    )
    args = parser.parse_args(argv)

    sema_root = args.sema.resolve()
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=sema_root,
        capture_output=True,
        text=True,
    ).stdout.strip()

    classes = gwsproto_classes()
    wanted = {
        type_name: (
            f"definitions/types/{type_name}/{version}.yaml"
            if version is not None
            else f"definitions/types/{type_name}.yaml"
        )
        for type_name, (_, version) in classes.items()
    }
    loaded = load_sema_definitions(sema_root, wanted)
    sema_types = loaded["registry"]["types"]
    schemas = loaded["schemas"]

    print(f"sema: {sema_root} (branch: {branch}) — {len(sema_types)} registered types")
    print(f"gwsproto: {len(classes)} named types with a TypeName\n")

    no_word: list[str] = []
    version_drift: list[str] = []
    example_reject: list[str] = []
    dump_drift: list[str] = []
    no_example: list[str] = []
    cli_reject: list[str] = []
    ok = 0

    for type_name in sorted(classes):
        cls, version = classes[type_name]
        entry = sema_types.get(type_name)
        if entry is None:
            no_word.append(f"{type_name}  ({cls.__name__})")
            continue

        latest = entry.get("latest_version")
        if version != latest:
            status = (entry.get("versions") or {}).get(version, {}).get("status")
            note = (
                f" [sema-side {version}: {status or 'NOT REGISTERED'}]"
                if version not in (entry.get("versions") or {}) or status
                else ""
            )
            version_drift.append(
                f"{type_name}  gwsproto {version} vs sema latest {latest}{note}"
            )

        schema = schemas.get(type_name)
        if schema is None:
            no_example.append(f"{type_name}  (no schema file for version {version})")
            continue
        examples = schema.get("examples") or []
        if not examples:
            no_example.append(f"{type_name}/{version}")
            continue

        failed = False
        for i, ex in enumerate(examples):
            doc = json.loads(ex)
            try:
                decoded = cls.model_validate(doc)
            except Exception as exc:  # noqa: BLE001 - report, don't crash the sweep
                example_reject.append(
                    f"{type_name}/{version} examples[{i}]: {str(exc)[:160]}"
                )
                failed = True
                continue
            dump = decoded.model_dump(by_alias=True, exclude_none=True, mode="json")
            if dump != doc:
                gone = sorted(set(doc) - set(dump))
                added = sorted(set(dump) - set(doc))
                changed = sorted(k for k in set(doc) & set(dump) if doc[k] != dump[k])
                dump_drift.append(
                    f"{type_name}/{version} examples[{i}]: "
                    f"missing={gone} extra={added} changed={changed}"
                )
                failed = True
                continue
            if args.cli:
                err = sema_cli_validate(sema_root, dump)
                if err:
                    cli_reject.append(f"{type_name}/{version} examples[{i}]: {err}")
                    failed = True
        if not failed:
            ok += 1
            if args.verbose:
                print(f"  OK  {type_name}/{version}")

    def section(title: str, items: list[str]) -> None:
        if items:
            print(f"\n== {title} ({len(items)}) ==")
            for item in items:
                print(f"  {item}")

    section("NO SEMA WORD — call out / add to sema", no_word)
    section("VERSION DRIFT — gwsproto not on sema latest", version_drift)
    section("EXAMPLE REJECT — gwsproto rejects canonical sema data", example_reject)
    section("DUMP DRIFT — gwsproto re-serialization is not canonical", dump_drift)
    section("SEMA CLI REJECT", cli_reject)
    section("NO EXAMPLE — nothing to decode (informational)", no_example)

    print(
        f"\n{ok} type(s) fully conformant; "
        f"{len(no_word)} without a word; {len(version_drift)} version drift; "
        f"{len(example_reject) + len(dump_drift) + len(cli_reject)} conformance failure(s)."
    )
    return 1 if (no_word or example_reject or dump_drift or cli_reject) else 0


if __name__ == "__main__":
    raise SystemExit(main())
