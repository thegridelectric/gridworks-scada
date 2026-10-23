#!/usr/bin/env bash
# Roll a house between lines, from the laptop: its scada on the pi and its
# LTN on the ltn box move together, with the layout pair verified against the
# committed tlayouts JSON both ways.
#
#   scripts/roll.sh <house> check                 what each pi and the LTN run:
#                                                 one line, the pushed tip of
#                                                 it, the same SHA on the pi and
#                                                 the LTN, and the committed pair
#                                                 of that line on both
#   scripts/roll.sh <house> forward               `to` jm/spruce-unlimbo, the
#                                                 one line a house rolls forward to
#   scripts/roll.sh <house> to <scada-branch>     check out the branch on the pi
#                                                 and on the LTN at its pushed
#                                                 SHA, verify (and on a y,
#                                                 install) the committed pair on
#                                                 the pi and on the LTN, restart
#                                                 the LTN, then the service
#   scripts/roll.sh <house> back                  `to` the house's roll-back line:
#                                                 actual-spruce for spruce,
#                                                 td/generalized-flo for the
#                                                 THOMAS_LTN houses (oak today),
#                                                 main for the rest
#
# <house> is spruce, beech, maple, oak, fir or elm. A house's second pi
# (<house>2, running scada2) is outside the roll.
#
# A house's LTN and scada run on exactly the same branch at the same pushed
# SHA. The LTN is the checkout ~/ltn-<house>/gridworks-scada on the ltn box,
# run by the systemd unit gwltn@<house> (service/gwltn@.service), and it
# loads the same layout pair as the scada from ~/ltn-<house>/.config/gridworks/ltn/.
# `check` reports the LTN beside the pi and fails when the two are on
# different lines, when either is behind the pushed tip of its line, when
# their SHAs differ, or when either's pair differs from the committed JSON;
# `to` moves the LTN checkout under the same guards as a pi's, verifies (and
# on a y, installs) its pair, and restarts its unit before the pi's service
# restarts, so the scada's first Report after the roll meets an LTN on its
# own line.
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
# box's file as <stem>.<date>-pre-roll.json. `back` keeps no copy, since the
# file it replaces is the committed file of the line rolled forward to, and
# removes the pre-roll copies the forward roll left.
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
LTN_BOX="${LTN_BOX:-ltn}"
LTN_REPO="~/ltn-$HOUSE/gridworks-scada"
LTN_UNIT="gwltn@$HOUSE"
LTN_CONFIG="~/ltn-$HOUSE/.config/gridworks/ltn"
FORWARD_LINE=jm/spruce-unlimbo
EVENT_DIR='~/.local/share/gridworks/scada/event'
# The unit files a pi installs (service/install); gwltn@.service is the ltn box's.
PI_UNITS='service/gwspaceheat.service service/gwspaceheat-restart.service service/gwspaceheat-restart.timer'
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
  check)   [ -z "$TARGET" ] || usage ;;
  forward) [ -z "$TARGET" ] || usage; TARGET="$FORWARD_LINE"; echo "$HOUSE: rolling forward to $TARGET" ;;
  to)      [ -n "$TARGET" ] || usage ;;
  back)  [ -z "$TARGET" ] || usage; TARGET="$(rollback_line "$HOUSE")"; echo "$HOUSE: rolling back to $TARGET" ;;
  *) usage ;;
esac

case "$HOUSE" in
  spruce|beech|maple|oak|fir|elm) ;;
  *) echo "unknown house $HOUSE"; exit 1 ;;
esac
PI="$HOUSE"
CONFIG_DIR='~/.config/gridworks/scada'
SERVICE=gwspaceheat

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
ltn_branch() { ssh -n "$LTN_BOX" "git -C $LTN_REPO branch --show-current"; }
ltn_sha()    { ssh -n "$LTN_BOX" "git -C $LTN_REPO rev-parse --short HEAD"; }
ltn_line()   { echo "ltn: $LTN_REPO on $(ltn_branch) @ $(ltn_sha); $LTN_UNIT $(ssh -n "$LTN_BOX" "systemctl is-active $LTN_UNIT")"; }
# Commits the box's checkout is behind the pushed tip of its own branch.
behind() { ssh -n "$1" "git -C $2 fetch -q origin && git -C $2 rev-list --count HEAD..origin/$3 2>/dev/null || echo ?"; }

# Verify one file of a box's pair against the committed JSON of a scada
# branch. Prints one line; returns 1 if it differs or is missing. With
# INSTALL=1 offers to install the committed file.
verify_file() { # <host> <label> <config-dir> <tlayouts-branch> <layout|ops>
  local host="$1" label="$2" cdir="$3" tlb="$4" kind="$5"
  local stem; [ "$kind" = layout ] && stem=hardware-layout || stem=operational-params
  local path; path="$(committed_path "$tlb" "$kind")" || { echo "  $label $stem: nothing committed under output/$HOUSE/ on tlayouts $tlb"; return 1; }
  local committed="$WORK/$label.$stem.committed.json" boxfile="$WORK/$label.$stem.box.json"
  git -C "$TLAYOUTS" show "origin/$tlb:$path" > "$committed"
  if ! ssh -n "$host" "cat $cdir/$stem.json" > "$boxfile" 2>/dev/null; then
    echo "  $label $stem: no $cdir/$stem.json on the box"
    [ "${INSTALL:-0}" = 1 ] && offer_install "$host" "$cdir" "$stem" "$committed" && return 0
    return 1
  fi
  if python3 "$COMPARE" "$kind" "$committed" "$boxfile" > "$WORK/$label.$stem.diff"; then
    echo "  $label $stem: matches tlayouts $tlb $path"
    return 0
  fi
  echo "  $label $stem: DIFFERS from tlayouts $tlb $path"
  sed 's/^/      /' "$WORK/$label.$stem.diff"
  [ "${INSTALL:-0}" = 1 ] && offer_install "$host" "$cdir" "$stem" "$committed" && return 0
  return 1
}

# Verify the pi's pair against a scada branch's committed JSON.
verify_pi() { # <scada-branch>
  local branch="$1" tlb rc=0
  tlb="$(tl_branch "$branch")" || { echo "  $PI: no tlayouts branch for scada branch $branch"; return 1; }
  verify_file "$PI" "$PI" "$CONFIG_DIR" "$tlb" layout || rc=1
  if reads_ops "$branch"; then
    verify_file "$PI" "$PI" "$CONFIG_DIR" "$tlb" ops || rc=1
    ssh -n "$PI" "[ -f $CONFIG_DIR/ta-deed.json ]" || { echo "  $PI: no $CONFIG_DIR/ta-deed.json; the branch needs it"; rc=1; }
  fi
  return $rc
}

# Verify the LTN's pair, the same committed JSON the pi runs.
verify_ltn() { # <scada-branch>
  local branch="$1" tlb rc=0
  tlb="$(tl_branch "$branch")" || { echo "  ltn: no tlayouts branch for scada branch $branch"; return 1; }
  verify_file "$LTN_BOX" ltn "$LTN_CONFIG" "$tlb" layout || rc=1
  if reads_ops "$branch"; then verify_file "$LTN_BOX" ltn "$LTN_CONFIG" "$tlb" ops || rc=1; fi
  return $rc
}

offer_install() { # <host> <config-dir> <stem> <committed-file>
  local pi="$1" cdir="$2" stem="$3" committed="$4"
  if [ "$VERB" = back ]; then
    read -r -p "  install the committed $stem on $pi (its pre-roll copies removed)? [y/N] " ans
    [ "$ans" = y ] || return 1
    ssh -n "$pi" "rm -f $cdir/$stem.*-pre-roll.json"
  else
    read -r -p "  install the committed $stem on $pi (box file kept as $stem.$STAMP-pre-roll.json)? [y/N] " ans
    [ "$ans" = y ] || return 1
    ssh -n "$pi" "[ ! -f $cdir/$stem.json ] || cp $cdir/$stem.json $cdir/$stem.$STAMP-pre-roll.json"
  fi
  scp -q "$committed" "$pi:$cdir/$stem.json"
  echo "  $pi $stem: installed"
}

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
git -C "$TLAYOUTS" fetch -q origin

if [ "$VERB" = check ]; then
  rc=0
  pb="$(box_branch "$PI")"; n="$(behind "$PI" "$BOX_REPO" "$pb")"
  echo "$PI: $BOX_REPO on $pb @ $(box_sha "$PI") (behind origin/$pb by $n); $SERVICE $(ssh -n "$PI" "systemctl is-active $SERVICE")"
  [ "$n" = 0 ] || { echo "$PI: not at the pushed tip of $pb"; rc=1; }
  verify_pi "$pb" || rc=1
  [ "$HOUSE" != spruce ] || echo "spruce: spruce-winter-hack $(ssh -n spruce 'systemctl is-active spruce-winter-hack; systemctl is-enabled spruce-winter-hack' | tr '\n' ' ')"
  lb="$(ltn_branch)"; n="$(behind "$LTN_BOX" "$LTN_REPO" "$lb")"
  echo "ltn: $LTN_REPO on $lb @ $(ltn_sha) (behind origin/$lb by $n); $LTN_UNIT $(ssh -n "$LTN_BOX" "systemctl is-active $LTN_UNIT")"
  [ "$n" = 0 ] || { echo "ltn: not at the pushed tip of $lb"; rc=1; }
  verify_ltn "$lb" || rc=1
  [ "$lb" = "$pb" ] || { echo "$HOUSE: LTN on $lb, scada on $pb; a house's LTN and scada run on one line"; rc=1; }
  [ "$(ltn_sha)" = "$(box_sha "$HOUSE")" ] || { echo "$HOUSE: LTN @ $(ltn_sha), scada @ $(box_sha "$HOUSE"); a house's LTN and scada run at one SHA"; rc=1; }
  exit $rc
fi

# ---- to <scada-branch> ----
tl_branch "$TARGET" > /dev/null || { echo "no tlayouts branch for scada branch $TARGET"; exit 1; }
echo "== ltn ($HOUSE)"
ssh -n "$LTN_BOX" "systemctl cat -q $LTN_UNIT" > /dev/null 2>&1 || { echo "ltn: no unit $LTN_UNIT on $LTN_BOX; install service/gwltn@.service first"; exit 1; }
ssh -n "$LTN_BOX" "git -C $LTN_REPO fetch -q origin"
[ -z "$(ssh -n "$LTN_BOX" "git -C $LTN_REPO status --porcelain")" ] || { echo "ltn: $LTN_REPO is dirty; refusing"; exit 1; }
ssh -n "$LTN_BOX" "git -C $LTN_REPO rev-parse --verify -q origin/$TARGET" > /dev/null || { echo "ltn: origin/$TARGET not on the box's remote; refusing"; exit 1; }
[ "$(ssh -n "$LTN_BOX" "git -C $LTN_REPO rev-list --count origin/$TARGET..$TARGET 2>/dev/null || echo 0")" = 0 ] || { echo "ltn: local $TARGET is ahead of origin/$TARGET; refusing"; exit 1; }
ltn_cur="$(ltn_sha)"
if [ -n "$(ssh -n "$LTN_BOX" "git -C $LTN_REPO diff --stat $ltn_cur origin/$TARGET -- gw_spaceheat/requirements packages/*/pyproject.toml")" ]; then
  echo "ltn: requirements differ between $ltn_cur and origin/$TARGET; rebuild the venv in $LTN_REPO (tools/mkenv.sh) after the checkout, by hand, then re-run"
  exit 1
fi
echo "== $PI"
ssh -n "$PI" "git -C $BOX_REPO fetch -q origin"
[ -z "$(ssh -n "$PI" "git -C $BOX_REPO status --porcelain")" ] || { echo "$PI: $BOX_REPO is dirty; refusing"; exit 1; }
ssh -n "$PI" "git -C $BOX_REPO rev-parse --verify -q origin/$TARGET" > /dev/null || { echo "$PI: origin/$TARGET not on the box's remote; refusing"; exit 1; }
cur="$(box_sha "$PI")"
if [ -n "$(ssh -n "$PI" "git -C $BOX_REPO diff --name-only $cur origin/$TARGET -- $PI_UNITS")" ]; then
  echo "$PI: service unit files differ between $cur and origin/$TARGET; root must reinstall them (service/install) after the checkout, by hand, then re-run"
  exit 1
fi
if [ -n "$(ssh -n "$PI" "git -C $BOX_REPO diff --stat $cur origin/$TARGET -- gw_spaceheat/requirements packages/*/pyproject.toml")" ]; then
  echo "$PI: requirements differ between $cur and origin/$TARGET; rebuild the venv on the box (tools/mkenv.sh) after the checkout, by hand, then re-run"
  ssh -n "$PI" "git -C $BOX_REPO diff --stat $cur origin/$TARGET -- gw_spaceheat/requirements packages/*/pyproject.toml"
  exit 1
fi
ssh -n "$PI" "git -C $BOX_REPO checkout -q $TARGET && git -C $BOX_REPO merge -q --ff-only origin/$TARGET" || { echo "$PI: checkout or fast-forward failed (local branch ahead of origin?); refusing"; exit 1; }
echo "$PI: $BOX_REPO on $TARGET @ $(box_sha "$PI") (was $cur)"
INSTALL=1 verify_pi "$TARGET" || { echo "$PI: pair not verified; service NOT restarted. Fix the pair and re-run."; exit 1; }

ssh -n "$LTN_BOX" "git -C $LTN_REPO checkout -q $TARGET && git -C $LTN_REPO merge -q --ff-only origin/$TARGET" || { echo "ltn: checkout or fast-forward failed; refusing. The pi is on $TARGET; fix the LTN checkout by hand and re-run."; exit 1; }
echo "ltn: $LTN_REPO on $TARGET @ $(ltn_sha) (was $ltn_cur)"
INSTALL=1 verify_ltn "$TARGET" || { echo "ltn: pair not verified; unit NOT restarted. Fix the pair and re-run."; exit 1; }
ssh -n "$LTN_BOX" "sudo systemctl restart $LTN_UNIT"; sleep 3
ltn_line

if [ "$HOUSE" = spruce ]; then
  if [ "$TARGET" = actual-spruce ]; then ssh -n spruce 'sudo systemctl enable -q --now spruce-winter-hack'; echo "spruce: winter hack enabled and started"
  else ssh -n spruce 'sudo systemctl disable -q --now spruce-winter-hack'; echo "spruce: winter hack stopped and disabled"; fi
fi
ssh -n "$PI" "sudo systemctl stop $SERVICE"
n="$(ssh -n "$PI" "E=$EVENT_DIR; Q=$EVENT_DIR.$STAMP-pre-roll-to-${TARGET//\//-}; n=\$(find \$E -type f 2>/dev/null | wc -l | tr -d ' '); if [ \"\$n\" != 0 ]; then mkdir -p \$Q && find \$E -mindepth 1 -maxdepth 1 -exec mv {} \$Q/ \; ; fi; echo \$n")"
echo "$PI: $n stored events set aside in $EVENT_DIR.$STAMP-pre-roll-to-${TARGET//\//-}"
ssh -n "$PI" "sudo systemctl start $SERVICE"; sleep 3
echo "$PI: $SERVICE $(ssh -n "$PI" "systemctl is-active $SERVICE") on $(box_branch "$PI") @ $(box_sha "$PI")"
echo "watch with: gwa watch $HOUSE"
