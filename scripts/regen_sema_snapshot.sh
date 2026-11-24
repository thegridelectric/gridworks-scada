#!/usr/bin/env bash
#
# regen_sema_snapshot.sh — regenerate the scada's vendored Sema snapshot
# (packages/gridworks-scada-protocol/sema_snapshot/sema) from the canonical
# sema repo, with `sema snapshot regen` on the seed
# packages/gridworks-scada-protocol/sema_seed_request.yaml. The seed states
# the staging policy (`staging.allow`), the package name and the vendor dir;
# there is no flag to pass.
#
# The snapshot is a TEST ORACLE: the hand-written gwsproto twins are checked
# against its generated classes by tests/named_types. It is committed, so a
# diff shows the vocabulary a scada speaks, and never shipped or run against
# a broker. The vendored tree is GENERATED: never hand-edit it; edit the seed
# (or the sema definitions) and re-run.
#
# The CLI refuses to run from a dirty sema checkout, so the snapshot is
# reproducible from the sema commit the checkout sits on; the snapshot's
# README records it.
#
# Usage:
#   scripts/regen_sema_snapshot.sh                 # sibling ../sema checkout
#   SEMA_REPO=/path/to/sema scripts/regen_sema_snapshot.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEMA_REPO="${SEMA_REPO:-$(cd "${REPO_ROOT}/../sema" 2>/dev/null && pwd || true)}"
SEED="${REPO_ROOT}/packages/gridworks-scada-protocol/sema_seed_request.yaml"

if [[ -z "${SEMA_REPO}" || ! -d "${SEMA_REPO}" ]]; then
  echo "error: sema repo not found." >&2
  echo "       set SEMA_REPO=/path/to/sema and re-run (default looked for a" >&2
  echo "       sibling checkout at ${REPO_ROOT}/../sema)." >&2
  exit 1
fi

echo "==> sema repo: ${SEMA_REPO} @ $(git -C "${SEMA_REPO}" rev-parse --short HEAD)"
cd "${SEMA_REPO}"
uv run sema snapshot regen "${SEED}"
echo "==> done. review the diff (git status) and run ./ci.sh."
