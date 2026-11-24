"""Check a vendored Sema snapshot against the seed that is committed beside it.

Shipped into every snapshot as ``check_staging.py`` and run by the consumer's
CI from the vendored tree alone, with no sema dependency:

    python -P <vendor-dir>/check_staging.py <committed seed> [--deploy-branch <name>]

``-P`` keeps the vendor dir off ``sys.path``: the snapshot's ``types/``
package sits beside this file and would otherwise shadow the standard
library's ``types`` module.

Fails when the snapshot holds a staging word the seed's ``staging.allow``
list does not name, or when the copy of the seed the snapshot was built from
(``indexes/seed_request.yaml``) differs from the committed seed. With
``--deploy-branch`` it also fails when the branch under test is that branch
and the snapshot holds any staging word, allowed or not: a deployed service
never runs a staging snapshot. The branch under test is the pull request's
target on GitHub Actions (``GITHUB_BASE_REF``), else the ref under test
(``GITHUB_REF_NAME``), else the checkout's current branch. A consumer that
rolls branches to its boxes passes no deploy branch. Both files the check
reads inside the snapshot are written by ``sema snapshot prepare`` in a fixed
shape, so the parse below is a line scan, standard library only.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def staging_marker(snapshot: Path) -> tuple[list[str], list[str]]:
    """(staging words held, words the seed allowed) from
    ``indexes/staging.yaml``; both empty when the snapshot holds no staging."""
    marker = snapshot / "indexes" / "staging.yaml"
    if not marker.exists():
        return [], []
    held: list[str] = []
    allowed: list[str] = []
    current: list[str] | None = None
    for raw in marker.read_text().splitlines():
        line = raw.rstrip()
        if line.startswith("staging_words:"):
            current = held
        elif line.startswith("staging_allow:"):
            current = allowed
        elif line.startswith("- ") and current is not None:
            current.append(line[2:].strip())
        elif line and not line.startswith(" "):
            current = None
    return held, allowed


def word_name(held: str) -> str:
    """``type flo.params:004`` -> ``flo.params``."""
    return held.split(" ", 1)[1].split(":", 1)[0]


def branch_under_test(checkout: Path) -> str | None:
    """The branch a CI run is judging: a pull request's target on GitHub
    Actions, else the pushed ref, else the checkout's branch; ``None`` when
    the checkout is not a git work tree or HEAD is detached."""
    for variable in ("GITHUB_BASE_REF", "GITHUB_REF_NAME"):
        value = os.environ.get(variable, "").strip()
        if value:
            return value
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "--short", "--quiet", "HEAD"],
            cwd=checkout,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_staging.py",
        description="Check a vendored Sema snapshot against its committed seed.",
    )
    parser.add_argument("seed", type=Path, help="the committed seed_request.yaml")
    parser.add_argument(
        "--deploy-branch",
        metavar="NAME",
        help="the branch deployed services run from; on it any staging word fails",
    )
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    snapshot = Path(__file__).resolve().parent
    committed_seed = args.seed.resolve()
    vendored_seed = snapshot / "indexes" / "seed_request.yaml"

    failures: list[str] = []
    if not vendored_seed.exists():
        failures.append(f"snapshot has no {vendored_seed.relative_to(snapshot)}")
    elif vendored_seed.read_bytes() != committed_seed.read_bytes():
        failures.append(
            f"{committed_seed} differs from the seed the snapshot was built from "
            f"({vendored_seed}); regenerate the snapshot"
        )

    held, allowed = staging_marker(snapshot)
    disallowed = sorted(w for w in held if word_name(w) not in set(allowed))
    if disallowed:
        failures.append(
            "snapshot holds staging words the seed does not allow:\n  "
            + "\n  ".join(disallowed)
        )

    if args.deploy_branch and held:
        branch = branch_under_test(committed_seed.parent)
        if branch == args.deploy_branch:
            failures.append(
                f"{branch} is the deploy branch and the snapshot holds staging "
                "words; a deployed service never runs a staging snapshot:\n  "
                + "\n  ".join(sorted(held))
            )

    if failures:
        print("check_staging: FAIL", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    held_note = f"{len(held)} allowed staging words" if held else "published-only"
    print(f"check_staging: OK ({held_note})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
