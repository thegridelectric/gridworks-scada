"""Compare what a roll must find equal before it moves a box.

Used by scripts/roll.sh. A layout matches only byte for byte. An
operational-params file matches when every field is equal, the
DispatchHold block included: the scada writes ServiceContractBroken
itself (the cold latch), so a box whose latch differs from the committed
file shows the difference, and the person at the roll decides whether
the committed file goes on.
An editable package's pyproject.toml matches when everything but its
own version line and its pins on the sibling editable packages is
equal: the box installs those packages editable from the checkout, so
neither changes what the venv resolves.

Usage: roll_compare.py layout|ops <committed.json> <box.json>
       roll_compare.py reqs <current-pyproject.toml> <target-pyproject.toml>
Exit 0 on a match; exit 1 with the differing paths or lines on stdout
otherwise.
"""

import json
import sys
from pathlib import Path

EDITABLE_PACKAGES = ("gridworks-scada-protocol", "gridworks-admin")


def flatten(value, prefix=""):
    """Dotted path -> leaf value; lists compare as one leaf."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            out.update(flatten(item, f"{prefix}.{key}" if prefix else key))
        return out
    return {prefix: json.dumps(value, sort_keys=True)}


def differing_paths(committed: dict, box: dict) -> list[str]:
    """Dotted leaf paths whose values differ."""
    a = flatten(committed)
    b = flatten(box)
    return [p for p in sorted(set(a) | set(b)) if a.get(p) != b.get(p)]


def layout_matches(committed: bytes, box: bytes) -> bool:
    return committed == box


def ops_differences(committed: dict, box: dict) -> list[str]:
    return differing_paths(committed, box)


def resolved_lines(pyproject: str) -> list[str]:
    """The lines of a pyproject.toml that bear on what a venv resolves."""
    kept = []
    for line in pyproject.splitlines():
        stripped = line.strip()
        if stripped.startswith("version ="):
            continue
        if any(stripped.startswith(f'"{name}') for name in EDITABLE_PACKAGES):
            continue
        kept.append(line)
    return kept


def requirements_differences(current: str, target: str) -> list[str]:
    a = resolved_lines(current)
    b = resolved_lines(target)
    return [f"- {line}" for line in a if line not in b] + [f"+ {line}" for line in b if line not in a]


def main(argv: list[str]) -> int:
    kind, committed_path, box_path = argv[1], Path(argv[2]), Path(argv[3])
    if kind == "layout":
        if layout_matches(committed_path.read_bytes(), box_path.read_bytes()):
            return 0
        committed = json.loads(committed_path.read_text())
        box = json.loads(box_path.read_text())
        diffs = differing_paths(committed, box)
        print("\n".join(diffs) if diffs else "same content, different bytes (key order or whitespace)")
        return 1
    if kind == "ops":
        committed = json.loads(committed_path.read_text())
        box = json.loads(box_path.read_text())
        diffs = ops_differences(committed, box)
        if not diffs:
            return 0
        print("\n".join(diffs))
        return 1
    if kind == "reqs":
        diffs = requirements_differences(committed_path.read_text(), box_path.read_text())
        if not diffs:
            return 0
        print("\n".join(diffs))
        return 1
    print(f"unknown kind {kind}; layout, ops or reqs", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
