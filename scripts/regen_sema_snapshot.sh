#!/usr/bin/env bash
#
# regen_sema_snapshot.sh — regenerate the scada's vendored Sema snapshot
# (packages/gridworks-scada-protocol/sema_snapshot/sema) from the canonical
# sema repo. Instance of sema's template_regen_snapshot.sh; the seed it
# consumes is packages/gridworks-scada-protocol/sema_seed_request.yaml.
#
# The snapshot is a TEST ORACLE: the hand-written gwsproto twins are checked
# against its generated classes by tests/named_types. It is committed, so a
# diff shows the vocabulary a scada speaks, and never shipped or run against
# a broker. The vendored tree is GENERATED —
# never hand-edit it; edit the seed (or the sema definitions) and re-run.
#
# --allow-staged: the contract and layout vocabulary is staging until it
# promotes, so this is a staging snapshot (marker in the indexes, README
# banner). As an oracle that never runs on a broker, the dev-only rule is met.
#
# The build mechanics are the sema CLI's (`sema snapshot --help` is the
# source of truth). The CLI refuses to run from a dirty sema checkout and
# writes only under <sema>/output, so the snapshot is reproducible from
# the sema commit the checkout sits on; the snapshot's README records it.
#
# Usage:
#   scripts/regen_sema_snapshot.sh                 # sibling ../sema checkout
#   SEMA_REPO=/path/to/sema scripts/regen_sema_snapshot.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEMA_REPO="${SEMA_REPO:-$(cd "${REPO_ROOT}/../sema" 2>/dev/null && pwd || true)}"

PACKAGE_NAME="sema_snapshot"
SEED="${REPO_ROOT}/packages/gridworks-scada-protocol/sema_seed_request.yaml"
VENDOR_DIR="${REPO_ROOT}/packages/gridworks-scada-protocol/sema_snapshot/sema"

if [[ -z "${SEMA_REPO}" || ! -d "${SEMA_REPO}" ]]; then
  echo "error: sema repo not found." >&2
  echo "       set SEMA_REPO=/path/to/sema and re-run (default looked for a" >&2
  echo "       sibling checkout at ${REPO_ROOT}/../sema)." >&2
  exit 1
fi

echo "==> sema repo: ${SEMA_REPO} @ $(git -C "${SEMA_REPO}" rev-parse --short HEAD)"
echo "==> seed:      ${SEED}"
echo "==> package:   ${PACKAGE_NAME}"

cd "${SEMA_REPO}"
echo "==> sema snapshot prepare --allow-staged"
uv run sema snapshot prepare --allow-staged "${SEED}"
echo "==> sema snapshot build --package-name ${PACKAGE_NAME}"
uv run sema snapshot build --package-name "${PACKAGE_NAME}"

echo "==> mirror ${SEMA_REPO}/output/sema -> ${VENDOR_DIR}"
mkdir -p "${VENDOR_DIR}"
rsync -a --delete --exclude='__pycache__' \
  "${SEMA_REPO}/output/sema/" "${VENDOR_DIR}/"

echo "==> done. review the diff (git status) and run your repo's tests."
