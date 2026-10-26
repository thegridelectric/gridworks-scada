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
#   scripts/roll.sh <house> forward               `to` main, the one line a
#                                                 house rolls forward to
#   scripts/roll.sh <house> to <scada-branch>     check out the branch on each pi
#                                                 and on the LTN at its pushed
#                                                 SHA, verify (and on a y,
#                                                 install) the committed pair on
#                                                 each pi and on the LTN, restart
#                                                 the LTN, then the services
#   scripts/roll.sh <house> back                  `to` the house's roll-back line:
#                                                 actual-spruce for spruce,
#                                                 td/generalized-flo for the
#                                                 THOMAS_LTN houses (oak today),
#                                                 legacy for the rest
#
# <house> is spruce, beech, maple, oak, fir or elm. Every house but spruce
# has a second pi, <house>2, whose scada2 runs from the same checkout
# (~/gridworks-scada) as the unit gwspaceheat2 (service2/, symlinked into
# systemd like service/ on the first pi), reads its pair from
# ~/.config/gridworks/scada2/ and keeps its events in
# ~/.local/share/gridworks/scada2/event/. The second pi is in the roll on
# the same footing as the first: same branch at the same pushed SHA, the
# same venv rule, the same committed pair byte for byte. The second pi
# reads the ops word on main as the first does; the ta.deed is
# the first pi's alone. scada2 reports its readings to the first pi by
# channel name with no encoding, so a second pi on another line's code or
# layout is reported by the first pi under the wrong units with nothing to
# catch it.
#
# A house's LTN and scadas run on exactly the same branch at the same pushed
# SHA. The LTN is the checkout ~/ltn-<house>/gridworks-scada on the ltn box,
# run by the systemd unit gwltn@<house> (service/gwltn@.service), and it
# loads the same layout pair as the scada from ~/ltn-<house>/.config/gridworks/ltn/.
# `check` reports the LTN beside the pis and fails when any two are on
# different lines, when any is behind the pushed tip of its line, when
# their SHAs differ, or when any pair differs from the committed JSON;
# `to` moves the LTN checkout under the same guards as a pi's, verifies (and
# on a y, installs) its pair, and restarts its unit before the pis' services
# restart, so the scada's first Report after the roll meets an LTN on its
# own line.
#
# Each scada branch has its tlayouts branch, and the committed JSON of that
# branch is the record of what the house runs:
#   main              -> tlayouts main
#   legacy            -> tlayouts legacy
#   actual-spruce     -> tlayouts actual-spruce
#   td/generalized-flo -> tlayouts legacy (the FLO work on oak: legacy's layout,
#                                          an LTN that differs)
# The source is the tlayouts REMOTE (git show origin/<branch>:<path> after a
# fetch), so only pushed JSON can reach a box, whatever the laptop's tlayouts
# checkout is doing. The box's scada checkout likewise moves only to a pushed
# SHA (fast-forward to origin/<branch>); a box ahead of its remote refuses.
#
# A layout matches byte for byte. On main the operational params
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
# restart timer and the service are stopped (as gwstop and gw2stop do; the
# timer alone would start the service at the next quarter hour), the event
# folder's contents are set aside as event.<date>-pre-roll-to-<branch>/, and
# the service and then the timer started.
#
# spruce: the winter hack (spruce-winter-hack.service) is the plant controller
# on actual-spruce and is disabled when the box moves off that line, enabled
# again when it moves back, so a reboot never runs two controllers.
#
# Requirements and units: if gw_spaceheat/requirements/ or the pi's unit
# files (service/ on the first pi, service2/ on the second) differ between the
# box's current SHA and the target, the roll stops before the checkout and
# says so; the venv is rebuilt (tools/mkenv.sh) or the units reinstalled
# (service/install, service2/install) by hand on the box, and the roll re-run.
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
FORWARD_LINE=main
# The unit files a pi installs (service/install, service2/install);
# gwltn@.service is the ltn box's.
PI_UNITS='service/gwspaceheat.service service/gwspaceheat-restart.service service/gwspaceheat-restart.timer'
PI2_UNITS='service2/gwspaceheat2.service service2/gwspaceheat2-restart.service service2/gwspaceheat2-restart.timer'
STAMP="$(date +%Y-%m-%d)"

usage() { sed -n '2,20p' "$0"; exit 1; }
[ -n "$HOUSE" ] && [ -n "$VERB" ] || usage
# Houses whose LTN runs Thomas's FLO work (td/generalized-flo): their roll-back
# line is that branch. Add a house here when its LTN moves onto it.
THOMAS_LTN="oak"
rollback_line() {
  case " $THOMAS_LTN " in *" $1 "*) echo td/generalized-flo; return ;; esac
  case "$1" in spruce) echo actual-spruce ;; *) echo legacy ;; esac
}
case "$VERB" in
  check)   [ -z "$TARGET" ] || usage ;;
  forward) [ -z "$TARGET" ] || usage; TARGET="$FORWARD_LINE"; echo "$HOUSE: rolling forward to $TARGET" ;;
  to)      [ -n "$TARGET" ] || usage ;;
  back)  [ -z "$TARGET" ] || usage; TARGET="$(rollback_line "$HOUSE")"; echo "$HOUSE: rolling back to $TARGET" ;;
  *) usage ;;
esac

case "$HOUSE" in
  spruce)                  PIS="spruce" ;;
  beech|maple|oak|fir|elm) PIS="$HOUSE ${HOUSE}2" ;;
  *) echo "unknown house $HOUSE"; exit 1 ;;
esac
# A pi named <house>2 is the second pi: scada2 config dir, unit, unit files, event dir.
is_second()  { [ "$1" != "${1%2}" ]; }
config_dir() { if is_second "$1"; then echo '~/.config/gridworks/scada2'; else echo '~/.config/gridworks/scada'; fi; }
service_of() { if is_second "$1"; then echo gwspaceheat2; else echo gwspaceheat; fi; }
units_of()   { if is_second "$1"; then echo "$PI2_UNITS"; else echo "$PI_UNITS"; fi; }
event_dir()  { if is_second "$1"; then echo '~/.local/share/gridworks/scada2/event'; else echo '~/.local/share/gridworks/scada/event'; fi; }

tl_branch() {
  case "$1" in
    main) echo main ;;
    legacy) echo legacy ;;
    actual-spruce) echo actual-spruce ;;
    td/generalized-flo) echo legacy ;;
    *) return 1 ;;
  esac
}
reads_ops() { [ "$1" = main ]; }

# The committed path of a file on a tlayouts branch: the deployed name first,
# then the names the tlayouts gens emit.
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

# Verify a pi's pair against a scada branch's committed JSON: the same
# committed files on both pis, the ta.deed on the first pi only.
verify_pi() { # <pi> <scada-branch>
  local pi="$1" branch="$2" tlb cdir rc=0
  tlb="$(tl_branch "$branch")" || { echo "  $pi: no tlayouts branch for scada branch $branch"; return 1; }
  cdir="$(config_dir "$pi")"
  verify_file "$pi" "$pi" "$cdir" "$tlb" layout || rc=1
  if reads_ops "$branch"; then
    verify_file "$pi" "$pi" "$cdir" "$tlb" ops || rc=1
    if ! is_second "$pi"; then
      ssh -n "$pi" "[ -f $cdir/ta-deed.json ]" || { echo "  $pi: no $cdir/ta-deed.json; the branch needs it"; rc=1; }
    fi
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
  pb="$(box_branch "$HOUSE")"
  for pi in $PIS; do
    b="$(box_branch "$pi")"; n="$(behind "$pi" "$BOX_REPO" "$b")"
    echo "$pi: $BOX_REPO on $b @ $(box_sha "$pi") (behind origin/$b by $n); $(service_of "$pi") $(ssh -n "$pi" "systemctl is-active $(service_of "$pi")")"
    [ "$n" = 0 ] || { echo "$pi: not at the pushed tip of $b"; rc=1; }
    verify_pi "$pi" "$b" || rc=1
    if is_second "$pi"; then
      [ "$b" = "$pb" ] || { echo "$HOUSE: $pi on $b, $HOUSE on $pb; a house's pis run on one line"; rc=1; }
      [ "$(box_sha "$pi")" = "$(box_sha "$HOUSE")" ] || { echo "$HOUSE: $pi @ $(box_sha "$pi"), $HOUSE @ $(box_sha "$HOUSE"); a house's pis run at one SHA"; rc=1; }
    fi
  done
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
for pi in $PIS; do
  echo "== $pi"
  svc="$(service_of "$pi")"
  ssh -n "$pi" "systemctl cat -q $svc" > /dev/null 2>&1 || { echo "$pi: no unit $svc; install it first"; exit 1; }
  ssh -n "$pi" "git -C $BOX_REPO fetch -q origin"
  [ -z "$(ssh -n "$pi" "git -C $BOX_REPO status --porcelain")" ] || { echo "$pi: $BOX_REPO is dirty; refusing"; exit 1; }
  ssh -n "$pi" "git -C $BOX_REPO rev-parse --verify -q origin/$TARGET" > /dev/null || { echo "$pi: origin/$TARGET not on the box's remote; refusing"; exit 1; }
  cur="$(box_sha "$pi")"
  if [ -n "$(ssh -n "$pi" "git -C $BOX_REPO diff --name-only $cur origin/$TARGET -- $(units_of "$pi")")" ]; then
    echo "$pi: service unit files differ between $cur and origin/$TARGET; root must reinstall them after the checkout, by hand, then re-run"
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

ssh -n "$LTN_BOX" "git -C $LTN_REPO checkout -q $TARGET && git -C $LTN_REPO merge -q --ff-only origin/$TARGET" || { echo "ltn: checkout or fast-forward failed; refusing. The pis are on $TARGET; fix the LTN checkout by hand and re-run."; exit 1; }
echo "ltn: $LTN_REPO on $TARGET @ $(ltn_sha) (was $ltn_cur)"
INSTALL=1 verify_ltn "$TARGET" || { echo "ltn: pair not verified; unit NOT restarted. Fix the pair and re-run."; exit 1; }
ssh -n "$LTN_BOX" "sudo systemctl restart $LTN_UNIT"; sleep 3
ltn_line

if [ "$HOUSE" = spruce ]; then
  if [ "$TARGET" = actual-spruce ]; then ssh -n spruce 'sudo systemctl enable -q --now spruce-winter-hack'; echo "spruce: winter hack enabled and started"
  else ssh -n spruce 'sudo systemctl disable -q --now spruce-winter-hack'; echo "spruce: winter hack stopped and disabled"; fi
fi
for pi in $PIS; do
  svc="$(service_of "$pi")"; edir="$(event_dir "$pi")"
  ssh -n "$pi" "sudo systemctl stop $svc-restart.timer $svc"
  n="$(ssh -n "$pi" "E=$edir; Q=$edir.$STAMP-pre-roll-to-${TARGET//\//-}; n=\$(find \$E -type f 2>/dev/null | wc -l | tr -d ' '); if [ \"\$n\" != 0 ]; then mkdir -p \$Q && find \$E -mindepth 1 -maxdepth 1 -exec mv {} \$Q/ \; ; fi; echo \$n")"
  echo "$pi: $n stored events set aside in $edir.$STAMP-pre-roll-to-${TARGET//\//-}"
  ssh -n "$pi" "sudo systemctl start $svc && sudo systemctl start $svc-restart.timer"; sleep 3
  echo "$pi: $svc $(ssh -n "$pi" "systemctl is-active $svc") on $(box_branch "$pi") @ $(box_sha "$pi")"
done
echo "watch with: gwa watch $HOUSE"
