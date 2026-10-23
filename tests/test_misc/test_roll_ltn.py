"""The roll script's ltn leg: a house's LTN and scada run on one line.

`scripts/roll.sh` reaches boxes only through `ssh`, so a stub `ssh` on PATH
answers for the pi and the ltn box from environment variables and logs
every command it is given. A throwaway tlayouts clone, with `output/spruce/`
committed on `actual-spruce` and pushed to a bare origin, is the record.
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
  *ltn-spruce*"branch --show-current"*) echo "$ROLL_STUB_LTN_BRANCH" ;;
  *"branch --show-current"*)            echo "$ROLL_STUB_PI_BRANCH" ;;
  *"rev-parse --short HEAD"*)           echo abc1234 ;;
  *"rev-parse --verify"*)               echo abc1234abc1234 ;;
  *"rev-list --count"*)                 echo 0 ;;
  *"status --porcelain"*|*"diff --"*|*"fetch"*) ;;
  *"systemctl cat"*)                    [ "$ROLL_STUB_LTN_UNIT" = present ] || exit 1 ;;
  *"is-active spruce-winter-hack"*)     printf 'active\nenabled\n' ;;
  *"is-active"*)                        echo active ;;
  *"cat ~/.config/gridworks/scada/hardware-layout.json"*) printf '%s' "$ROLL_STUB_LAYOUT" ;;
  *"cat ~/ltn-spruce/.config/gridworks/ltn/hardware-layout.json"*) printf '%s' "$ROLL_STUB_LAYOUT" ;;
  *"find"*)                             echo 0 ;;
  *) ;;
esac
"""


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture
def roll_env(tmp_path: Path) -> dict[str, str]:
    origin = tmp_path / "tlayouts-origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    work = tmp_path / "tlayouts"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    git(work, "config", "user.email", "t@t")
    git(work, "config", "user.name", "t")
    git(work, "checkout", "-q", "-b", "actual-spruce")
    (work / "output" / "spruce").mkdir(parents=True)
    (work / "output" / "spruce" / "hardware-layout.json").write_text(LAYOUT)
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "spruce record")
    git(work, "push", "-q", "origin", "actual-spruce")

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
        ROLL_STUB_PI_BRANCH="actual-spruce",
        ROLL_STUB_LTN_BRANCH="actual-spruce",
        ROLL_STUB_LTN_UNIT="present",
    )
    return env


def run_roll(env: dict[str, str], *args: str, answers: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(ROLL), "spruce", *args], env=env, capture_output=True, text=True, input=answers)


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
    scada_start = next(i for i, l in enumerate(log) if l == "spruce: sudo systemctl start gwspaceheat")
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
