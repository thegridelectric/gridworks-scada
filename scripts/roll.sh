#!/usr/bin/env bash
# Roll a house's scada between lines, from the laptop, with the layout pair
# verified against the committed tlayouts JSON both ways.
#
#   scripts/roll.sh <house> check                 what each pi runs, and whether
#                                                 its pair matches the committed
#                                                 JSON of the line it is on
#   scripts/roll.sh <house> to <scada-branch>     check out the branch on each pi
#                                                 at its pushed SHA, verify (and
#                                                 on a y, install) the committed
#                                                 pair, restart the service
#   scripts/roll.sh <house> back                  `to` the house's roll-back line:
#                                                 actual-spruce for spruce,
#                                                 td/generalized-flo for the
#                                                 THOMAS_LTN houses (oak today),
#                                                 main for the rest
#
# <house> is spruce, beech, maple, oak, fir or elm; every house but spruce has
# a second pi, <house>2, whose scada2 reads ~/.config/gridworks/scada2/.
#
# Each scada branch has its tlayouts branch, and the committed JSON of that
# branch is the record of what the house runs:
#   main              -> tlayouts main
#   actual-spruce     -> tlayouts actual-spruce
#   jm/spruce-unlimbo -> tlayouts jm/spruce
#   td/generalized-flo -> tlayouts main   (the FLO work on oak: main's layout,
#                                          an LTN that differs)
# The source is the tlayouts REMOTE (git show origin/<branch>:<path> after a
# fetch), so only pushed JSON can reach a box, whatever the laptop's tlayouts
# checkout is doing. The box's scada checkout likewise moves only to a pushed
# SHA (fast-forward to origin/<branch>); a box ahead of its remote refuses.
#
# A layout matches byte for byte. On jm/spruce-unlimbo the operational params
# match except for the DispatchHold block, which the scada writes itself
# (scripts/roll_compare.py). On the other lines the scada does not read the
# ops word and the file is left alone. A pi whose file differs shows the
# differing paths and installs the committed file only on a y, keeping the
# box's file as <stem>.<date>-pre-roll.json.
#
# A second pi is left alone: `to` neither moves its checkout nor restarts
# its service. Its layout is compared on the part scada2 senses (the s2
# hierarchy, its components and cacs, the channels it captures); the rest of
# its file is the primary's and may differ. A sensed-part difference is
# reported and the roll stops, and the fix is made by hand.
#
# Stored events do not cross lines. The scada persists every event it has not
# had acked (~/.local/share/gridworks/scada/event/) and re-sends them on each
# link-up; an event written by one line's scada is not acked by the other
# line's LTN, and the link flaps on it every ack timeout for good. So the
# service is stopped, the event folder's contents are set aside as
# event.<date>-pre-roll-to-<branch>/, and the service started.
#
# spruce: the winter hack (spruce-winter-hack.service) is the plant controller
# on actual-spruce and is disabled when the box moves off that line, enabled
# again when it moves back, so a reboot never runs two controllers.
#
# Requirements and units: if gw_spaceheat/requirements/ or service/ unit files
# differ between the box's current SHA and the target, the roll stops before
# the checkout and says so; the venv is rebuilt (tools/mkenv.sh) or the units
# reinstalled (service/install) by hand on the box, and the roll re-run.
set -euo pipefail

HOUSE="${1:-}"; VERB="${2:-}"; TARGET="${3:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
TLAYOUTS="${TLAYOUTS_DIR:-$HERE/../../tlayouts}"
COMPARE="$HERE/roll_compare.py"
BOX_REPO='~/gridworks-scada'
EVENT_DIR='~/.local/share/gridworks/scada/event'
STAMP="$(date +%Y-%m-%d)"

usage() { sed -n '2,20p' "$0"; exit 1; }
[ -n "$HOUSE" ] && [ -n "$VERB" ] || usage
# Houses whose LTN runs Thomas's FLO work (td/generalized-flo): their roll-back
# line is that branch. Add a house here when its LTN moves onto it.
THOMAS_LTN="oak"
rollback_line() {
  case " $THOMAS_LTN " in *" $1 "*) echo td/generalized-flo; return ;; esac
  case "$1" in spruce) echo actual-spruce ;; *) echo main ;; esac
}
case "$VERB" in
  check) [ -z "$TARGET" ] || usage ;;
  to)    [ -n "$TARGET" ] || usage ;;
  back)  [ -z "$TARGET" ] || usage; TARGET="$(rollback_line "$HOUSE")"; echo "$HOUSE: rolling back to $TARGET" ;;
  *) usage ;;
esac

case "$HOUSE" in
  spruce)                 PIS="spruce" ;;
  beech|maple|oak|fir|elm) PIS="$HOUSE ${HOUSE}2" ;;
  *) echo "unknown house $HOUSE"; exit 1 ;;
esac

tl_branch() {
  case "$1" in
    main) echo main ;;
    actual-spruce) echo actual-spruce ;;
    jm/spruce-unlimbo) echo jm/spruce ;;
    td/generalized-flo) echo main ;;
    *) return 1 ;;
  esac
}
reads_ops() { [ "$1" = jm/spruce-unlimbo ]; }
config_dir() { case "$1" in *2) echo '~/.config/gridworks/scada2' ;; *) echo '~/.config/gridworks/scada' ;; esac; }
service_of() { case "$1" in *2) echo gwspaceheat2 ;; *) echo gwspaceheat ;; esac; }

# The committed path of a file on a tlayouts branch: the deployed name first,
# then the names the jm/spruce gens emit.
committed_path() { # <tlayouts-branch> <layout|ops>
  local b="$1" kind="$2" candidates
  if [ "$kind" = layout ]; then
    candidates="hardware-layout.json hardware-layout.generated.json gw.nolan.layout.json gw.house0.layout.json"
  else
    candidates="operational-params.json operational-params.generated.json gw.nolan.operational.params.json gw.house0.operational.params.json"
  fi
  for c in $candidates; do
    if git -C "$TLAYOUTS" cat-file -e "origin/$b:output/$HOUSE/$c" 2>/dev/null; then echo "output/$HOUSE/$c"; return 0; fi
  done
  return 1
}

box_branch() { ssh -n "$1" "git -C $BOX_REPO branch --show-current"; }
box_sha()    { ssh -n "$1" "git -C $BOX_REPO rev-parse --short HEAD"; }

# Verify one pi's pair against a scada branch's committed JSON. Prints a line
# per file; returns 1 if anything differs. With INSTALL=1 offers to install.
verify_pi() { # <pi> <scada-branch>
  local pi="$1" branch="$2" tlb cdir rc=0
  tlb="$(tl_branch "$branch")" || { echo "  $pi: no tlayouts branch for scada branch $branch"; return 1; }
  cdir="$(config_dir "$pi")"
  local kinds="layout"; reads_ops "$branch" && kinds="layout ops"
  for kind in $kinds; do
    local stem compare="$kind"; [ "$kind" = layout ] && stem=hardware-layout || stem=operational-params
    local offer=1; if [ "$kind" = layout ] && [ "$pi" != "${pi%2}" ]; then compare=sensed; offer=0; fi
    local path; path="$(committed_path "$tlb" "$kind")" || { echo "  $pi $stem: nothing committed under output/$HOUSE/ on tlayouts $tlb"; rc=1; continue; }
    local committed="$WORK/$pi.$stem.committed.json" boxfile="$WORK/$pi.$stem.box.json"
    git -C "$TLAYOUTS" show "origin/$tlb:$path" > "$committed"
    if ! ssh -n "$pi" "cat $cdir/$stem.json" > "$boxfile" 2>/dev/null; then
      echo "  $pi $stem: no $cdir/$stem.json on the box"
      [ "$kind" = ops ] && [ "${INSTALL:-0}" = 1 ] && offer_install "$pi" "$cdir" "$stem" "$committed" || rc=1
      continue
    fi
    if python3 "$COMPARE" "$compare" "$committed" "$boxfile" > "$WORK/$pi.$stem.diff"; then
      [ "$compare" = sensed ] && echo "  $pi $stem: sensed part matches tlayouts $tlb $path" || echo "  $pi $stem: matches tlayouts $tlb $path"
    else
      [ "$compare" = sensed ] && echo "  $pi $stem: sensed part DIFFERS from tlayouts $tlb $path" || echo "  $pi $stem: DIFFERS from tlayouts $tlb $path"
      sed 's/^/      /' "$WORK/$pi.$stem.diff"
      if [ "${INSTALL:-0}" = 1 ] && [ "$offer" = 1 ]; then offer_install "$pi" "$cdir" "$stem" "$committed" || rc=1; else rc=1; fi
    fi
  done
  if reads_ops "$branch" && ! ssh -n "$pi" "[ -f $cdir/ta-deed.json ]"; then echo "  $pi: no $cdir/ta-deed.json; the branch needs it"; rc=1; fi
  return $rc
}

offer_install() { # <pi> <config-dir> <stem> <committed-file>
  local pi="$1" cdir="$2" stem="$3" committed="$4"
  read -r -p "  install the committed $stem on $pi (box file kept as $stem.$STAMP-pre-roll.json)? [y/N] " ans
  [ "$ans" = y ] || return 1
  ssh -n "$pi" "[ ! -f $cdir/$stem.json ] || cp $cdir/$stem.json $cdir/$stem.$STAMP-pre-roll.json"
  scp -q "$committed" "$pi:$cdir/$stem.json"
  echo "  $pi $stem: installed"
}

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
git -C "$TLAYOUTS" fetch -q origin

if [ "$VERB" = check ]; then
  rc=0
  for pi in $PIS; do
    b="$(box_branch "$pi")"; echo "$pi: $BOX_REPO on $b @ $(box_sha "$pi"); $(service_of "$pi") $(ssh -n "$pi" "systemctl is-active $(service_of "$pi")")"
    verify_pi "$pi" "$b" || rc=1
  done
  [ "$HOUSE" != spruce ] || echo "spruce: spruce-winter-hack $(ssh -n spruce 'systemctl is-active spruce-winter-hack; systemctl is-enabled spruce-winter-hack' | tr '\n' ' ')"
  exit $rc
fi

# ---- to <scada-branch> ----
tl_branch "$TARGET" > /dev/null || { echo "no tlayouts branch for scada branch $TARGET"; exit 1; }
for pi in $PIS; do
  echo "== $pi"
  if [ "$pi" != "${pi%2}" ]; then
    verify_pi "$pi" "$TARGET" || { echo "$pi: what scada2 senses differs from the record; fix it by hand and re-run."; exit 1; }
    continue
  fi
  ssh -n "$pi" "git -C $BOX_REPO fetch -q origin"
  [ -z "$(ssh -n "$pi" "git -C $BOX_REPO status --porcelain")" ] || { echo "$pi: $BOX_REPO is dirty; refusing"; exit 1; }
  ssh -n "$pi" "git -C $BOX_REPO rev-parse --verify -q origin/$TARGET" > /dev/null || { echo "$pi: origin/$TARGET not on the box's remote; refusing"; exit 1; }
  cur="$(box_sha "$pi")"
  if [ -n "$(ssh -n "$pi" "git -C $BOX_REPO diff --name-only $cur origin/$TARGET -- 'service/*.service' 'service/*.timer'")" ]; then
    echo "$pi: service unit files differ between $cur and origin/$TARGET; root must reinstall them (service/install) after the checkout, by hand, then re-run"
    exit 1
  fi
  if [ -n "$(ssh -n "$pi" "git -C $BOX_REPO diff --stat $cur origin/$TARGET -- gw_spaceheat/requirements packages/*/pyproject.toml")" ]; then
    echo "$pi: requirements differ between $cur and origin/$TARGET; rebuild the venv on the box (tools/mkenv.sh) after the checkout, by hand, then re-run"
    ssh -n "$pi" "git -C $BOX_REPO diff --stat $cur origin/$TARGET -- gw_spaceheat/requirements packages/*/pyproject.toml"
    exit 1
  fi
  ssh -n "$pi" "git -C $BOX_REPO checkout -q $TARGET && git -C $BOX_REPO merge -q --ff-only origin/$TARGET" || { echo "$pi: checkout or fast-forward failed (local branch ahead of origin?); refusing"; exit 1; }
  echo "$pi: $BOX_REPO on $TARGET @ $(box_sha "$pi") (was $cur)"
  INSTALL=1 verify_pi "$pi" "$TARGET" || { echo "$pi: pair not verified; service NOT restarted. Fix the pair and re-run."; exit 1; }
done

if [ "$HOUSE" = spruce ]; then
  if [ "$TARGET" = actual-spruce ]; then ssh -n spruce 'sudo systemctl enable -q --now spruce-winter-hack'; echo "spruce: winter hack enabled and started"
  else ssh -n spruce 'sudo systemctl disable -q --now spruce-winter-hack'; echo "spruce: winter hack stopped and disabled"; fi
fi
for pi in $PIS; do
  [ "$pi" = "${pi%2}" ] || continue
  svc="$(service_of "$pi")"
  ssh -n "$pi" "sudo systemctl stop $svc"
  n="$(ssh -n "$pi" "E=$EVENT_DIR; Q=$EVENT_DIR.$STAMP-pre-roll-to-${TARGET//\//-}; n=\$(find \$E -type f 2>/dev/null | wc -l | tr -d ' '); if [ \"\$n\" != 0 ]; then mkdir -p \$Q && find \$E -mindepth 1 -maxdepth 1 -exec mv {} \$Q/ \; ; fi; echo \$n")"
  echo "$pi: $n stored events set aside in $EVENT_DIR.$STAMP-pre-roll-to-${TARGET//\//-}"
  ssh -n "$pi" "sudo systemctl start $svc"; sleep 3
  echo "$pi: $svc $(ssh -n "$pi" "systemctl is-active $svc") on $(box_branch "$pi") @ $(box_sha "$pi")"
done
echo "watch with: gwa watch $HOUSE"
