"""The roll script's legs: a house's LTN and its pis run on one line.

`scripts/roll.sh` reaches boxes only through `ssh`, so a stub `ssh` on PATH
answers for the pis and the ltn box from environment variables and logs
every command it is given. A throwaway tlayouts clone, with the house's
`output/<house>/` committed on its line and pushed to a bare origin, is the
record. spruce has one pi; maple has a second pi, maple2, running scada2.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROLL = Path(__file__).parents[2] / "scripts" / "roll.sh"
LAYOUT = '{"LayoutId": "spruce-test"}\n'

SSH_STUB = r"""#!/usr/bin/env bash
# roll.sh test double: $1 is the host (after -n), the rest is the command.
[ "$1" = -n ] && shift
host="$1"; shift; cmd="$*"
echo "$host: $cmd" >> "$ROLL_STUB_LOG"
case "$cmd" in
  *ltn-*"branch --show-current"*)       echo "$ROLL_STUB_LTN_BRANCH" ;;
  *"branch --show-current"*)            if [ "$host" = "${host%2}" ]; then echo "$ROLL_STUB_PI_BRANCH"; else echo "$ROLL_STUB_PI2_BRANCH"; fi ;;
  *"rev-parse --short HEAD"*)           if [ "$host" = "${host%2}" ]; then echo abc1234; else echo "$ROLL_STUB_PI2_SHA"; fi ;;
  *"rev-parse --verify"*)               echo abc1234abc1234 ;;
  *"rev-list --count"*)                 echo 0 ;;
  *"status --porcelain"*|*"diff --"*|*"fetch"*) ;;
  *"systemctl cat"*)                    [ "$ROLL_STUB_LTN_UNIT" = present ] || exit 1 ;;
  *"is-active spruce-winter-hack"*)     printf 'active\nenabled\n' ;;
  *"is-active"*)                        echo active ;;
  *"cat ~/.config/gridworks/scada/hardware-layout.json"*) printf '%s' "$ROLL_STUB_LAYOUT" ;;
  *"cat ~/.config/gridworks/scada2/hardware-layout.json"*) printf '%s' "$ROLL_STUB_PI2_LAYOUT" ;;
  *"cat ~/ltn-"*"/.config/gridworks/ltn/hardware-layout.json"*) printf '%s' "$ROLL_STUB_LAYOUT" ;;
  *"find"*)                             echo 0 ;;
  *) ;;
esac
"""


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def make_env(tmp_path: Path, house: str, line: str) -> dict[str, str]:
    """A record with `output/<house>/` committed on tlayouts `line`, the ssh
    stub on PATH, and every box of the house on `line` with the committed
    layout."""
    origin = tmp_path / "tlayouts-origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    work = tmp_path / "tlayouts"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    git(work, "config", "user.email", "t@t")
    git(work, "config", "user.name", "t")
    git(work, "checkout", "-q", "-b", line)
    (work / "output" / house).mkdir(parents=True)
    (work / "output" / house / "hardware-layout.json").write_text(LAYOUT)
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", f"{house} record")
    git(work, "push", "-q", "origin", line)

    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "ssh"
    stub.write_text(SSH_STUB)
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    (bindir / "scp").write_text("#!/usr/bin/env bash\nexit 0\n")
    (bindir / "scp").chmod(0o755)

    env = dict(os.environ)
    env.update(
        PATH=f"{bindir}:{env['PATH']}",
        TLAYOUTS_DIR=str(work),
        ROLL_STUB_LOG=str(tmp_path / "ssh.log"),
        ROLL_STUB_LAYOUT=LAYOUT,
        ROLL_STUB_PI2_LAYOUT=LAYOUT,
        ROLL_STUB_PI_BRANCH=line,
        ROLL_STUB_PI2_BRANCH=line,
        ROLL_STUB_PI2_SHA="abc1234",
        ROLL_STUB_LTN_BRANCH=line,
        ROLL_STUB_LTN_UNIT="present",
        ROLL_HOUSE=house,
    )
    return env


@pytest.fixture
def roll_env(tmp_path: Path) -> dict[str, str]:
    return make_env(tmp_path, "spruce", "actual-spruce")


@pytest.fixture
def maple_env(tmp_path: Path) -> dict[str, str]:
    return make_env(tmp_path, "maple", "legacy")


def run_roll(env: dict[str, str], *args: str, answers: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(ROLL), env["ROLL_HOUSE"], *args], env=env, capture_output=True, text=True, input=answers)


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_check_reports_ltn_beside_the_pi(roll_env: dict[str, str]) -> None:
    r = run_roll(roll_env, "check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ltn: ~/ltn-spruce/gridworks-scada on actual-spruce @ abc1234 (behind origin/actual-spruce by 0); gwltn@spruce active" in r.stdout


def test_check_fails_when_ltn_and_scada_are_on_different_lines(roll_env: dict[str, str]) -> None:
    roll_env["ROLL_STUB_LTN_BRANCH"] = "main"
    r = run_roll(roll_env, "check")
    assert r.returncode == 1
    assert "spruce: LTN on main, scada on actual-spruce; a house's LTN and scada run on one line" in r.stdout


def test_to_refuses_without_the_ltn_unit(roll_env: dict[str, str]) -> None:
    roll_env["ROLL_STUB_LTN_UNIT"] = "absent"
    r = run_roll(roll_env, "to", "actual-spruce")
    assert r.returncode == 1
    assert "ltn: no unit gwltn@spruce on ltn; install service/gwltn@.service first" in r.stdout
    log = Path(roll_env["ROLL_STUB_LOG"]).read_text()
    assert "checkout" not in log


def test_to_moves_the_ltn_and_restarts_it_before_the_scada(roll_env: dict[str, str]) -> None:
    r = run_roll(roll_env, "to", "actual-spruce")
    assert r.returncode == 0, r.stdout + r.stderr
    log = Path(roll_env["ROLL_STUB_LOG"]).read_text().splitlines()
    ltn_checkout = next(i for i, l in enumerate(log) if l.startswith("ltn: git -C ~/ltn-spruce/gridworks-scada checkout -q actual-spruce"))
    ltn_restart = next(i for i, l in enumerate(log) if l == "ltn: sudo systemctl restart gwltn@spruce")
    scada_start = next(i for i, l in enumerate(log) if l == "spruce: sudo systemctl start gwspaceheat && sudo systemctl start gwspaceheat-restart.timer")
    assert ltn_checkout < ltn_restart < scada_start


def test_to_keeps_the_box_file_as_a_pre_roll_copy(roll_env: dict[str, str]) -> None:
    roll_env["ROLL_STUB_LAYOUT"] = '{"LayoutId": "spruce-other"}\n'
    r = run_roll(roll_env, "to", "actual-spruce", answers="y\ny\n")
    assert r.returncode == 0, r.stdout + r.stderr
    log = Path(roll_env["ROLL_STUB_LOG"]).read_text()
    assert "cp ~/.config/gridworks/scada/hardware-layout.json ~/.config/gridworks/scada/hardware-layout." in log
    assert "pre-roll.json" in log and "rm -f" not in log


def test_back_removes_the_pre_roll_copies_and_keeps_none(roll_env: dict[str, str]) -> None:
    roll_env["ROLL_STUB_LAYOUT"] = '{"LayoutId": "spruce-other"}\n'
    r = run_roll(roll_env, "back", answers="y\ny\n")
    assert r.returncode == 0, r.stdout + r.stderr
    log = Path(roll_env["ROLL_STUB_LOG"]).read_text()
    assert "spruce: rm -f ~/.config/gridworks/scada/hardware-layout.*-pre-roll.json" in log
    assert "ltn: rm -f ~/ltn-spruce/.config/gridworks/ltn/hardware-layout.*-pre-roll.json" in log
    assert "cp ~/" not in log


def test_check_reports_the_second_pi_beside_the_first(maple_env: dict[str, str]) -> None:
    r = run_roll(maple_env, "check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "maple2: ~/gridworks-scada on legacy @ abc1234 (behind origin/legacy by 0); gwspaceheat2 active" in r.stdout
    assert "maple2 hardware-layout: matches tlayouts legacy output/maple/hardware-layout.json" in r.stdout


def test_check_fails_when_the_pis_are_on_different_lines_or_shas(maple_env: dict[str, str]) -> None:
    maple_env["ROLL_STUB_PI2_BRANCH"] = "main"
    r = run_roll(maple_env, "check")
    assert r.returncode == 1
    assert "maple: maple2 on main, maple on legacy; a house's pis run on one line" in r.stdout
    maple_env["ROLL_STUB_PI2_BRANCH"] = "legacy"
    maple_env["ROLL_STUB_PI2_SHA"] = "def5678"
    r = run_roll(maple_env, "check")
    assert r.returncode == 1
    assert "maple: maple2 @ def5678, maple @ abc1234; a house's pis run at one SHA" in r.stdout


def test_to_moves_both_pis_and_installs_the_second_pi_s_pair_in_its_own_dir(maple_env: dict[str, str]) -> None:
    maple_env["ROLL_STUB_PI2_LAYOUT"] = '{"LayoutId": "maple-stale"}\n'
    r = run_roll(maple_env, "to", "legacy", answers="y\n")
    assert r.returncode == 0, r.stdout + r.stderr
    log = Path(maple_env["ROLL_STUB_LOG"]).read_text().splitlines()
    assert "maple: git -C ~/gridworks-scada checkout -q legacy && git -C ~/gridworks-scada merge -q --ff-only origin/legacy" in log
    assert "maple2: git -C ~/gridworks-scada checkout -q legacy && git -C ~/gridworks-scada merge -q --ff-only origin/legacy" in log
    assert any(line.startswith("maple2: git -C ~/gridworks-scada diff --name-only abc1234 origin/legacy -- service2/gwspaceheat2.service") for line in log)
    assert any(line.startswith("maple2: [ ! -f ~/.config/gridworks/scada2/hardware-layout.json ] || cp ~/.config/gridworks/scada2/hardware-layout.json ~/.config/gridworks/scada2/hardware-layout.") for line in log)
    ltn_restart = log.index("ltn: sudo systemctl restart gwltn@maple")
    first = log.index("maple: sudo systemctl start gwspaceheat && sudo systemctl start gwspaceheat-restart.timer")
    second = log.index("maple2: sudo systemctl start gwspaceheat2 && sudo systemctl start gwspaceheat2-restart.timer")
    assert "maple2: sudo systemctl stop gwspaceheat2-restart.timer gwspaceheat2" in log
    assert ltn_restart < first < second
    assert any("maple2: E=~/.local/share/gridworks/scada2/event;" in line for line in log)


def test_back_sends_a_house0_house_to_legacy(maple_env: dict[str, str]) -> None:
    r = run_roll(maple_env, "back", answers="y\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "maple: rolling back to legacy" in r.stdout
    log = Path(maple_env["ROLL_STUB_LOG"]).read_text().splitlines()
    assert "maple: git -C ~/gridworks-scada checkout -q legacy && git -C ~/gridworks-scada merge -q --ff-only origin/legacy" in log


def test_forward_sends_a_house_to_main(maple_env: dict[str, str]) -> None:
    r = run_roll(maple_env, "forward", answers="y\n")
    assert "maple: rolling forward to main" in r.stdout


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_to_a_branch_off_main_reads_the_main_record(maple_env: dict[str, str]) -> None:
    """A scada branch not in the line table is on the main line: its pair is
    tlayouts main's, it reads the ops word, and the box checks out the branch."""
    work = Path(maple_env["TLAYOUTS_DIR"])
    git(work, "checkout", "-q", "-b", "main")
    (work / "output" / "maple" / "operational-params.json").write_text('{"Ops": "maple-test"}\n')
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "maple main record")
    git(work, "push", "-q", "origin", "main")
    r = run_roll(maple_env, "to", "jm/trial", answers="y\ny\ny\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "maple hardware-layout: matches tlayouts main output/maple/hardware-layout.json" in r.stdout
    assert "maple operational-params:" in r.stdout
    log = Path(maple_env["ROLL_STUB_LOG"]).read_text().splitlines()
    assert "maple: git -C ~/gridworks-scada checkout -q jm/trial && git -C ~/gridworks-scada merge -q --ff-only origin/jm/trial" in log
