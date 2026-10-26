"""Once per run, when the upstream link can first carry a publish, a scada
sends its layout.lite, the home's ta.deed, or a Warning when it holds no
deed (no-ta-deed) or a deed for another terminal asset (ta-deed-wrong-asset),
its operating status, and the git commit it is running. No LTN is needed for
any of it."""

import asyncio
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
import actors.scada
from actors.scada import SCADA_REPO_ROOT, Scada, git_commit_of
from gwproactor.config import Paths
from gwsproto.enums import LogLevel, TaValidationState
from gwsproto.named_types import Glitch, HouseOperatingStatus, LayoutLite, ScadaCommit, TaDeed
from scada_app import ScadaApp
from tests.utils.scada_live_test_helper import ScadaLiveTest


def remove_deed() -> None:
    # The autouse fixture seeds a ValidatedSimulatedAsset deed.
    Path(Paths(name="scada").hardware_layout).parent.joinpath("ta-deed.json").unlink()


def deed_another_asset() -> TaDeed:
    """Rewrites the seeded deed with a TaId that is not the layout's
    terminal asset, and returns it."""
    path = Path(Paths(name="scada").hardware_layout).parent.joinpath("ta-deed.json")
    deed = TaDeed.model_validate_json(path.read_text())
    other = deed.model_copy(update={"TaId": str(uuid.uuid4())})
    path.write_text(other.model_dump_json(by_alias=True))
    return other


async def no_announcer(self: Scada) -> None:
    """Stands in for the announcer task, so a test's own call is the only
    send."""


def record_sends(monkeypatch: pytest.MonkeyPatch, scada: Scada) -> list[Any]:
    sent: list[Any] = []
    monkeypatch.setattr(
        scada, "_send_to", lambda to_node, payload, from_node=None: sent.append(payload)
    )
    return sent


@pytest.mark.asyncio
async def test_ta_deed_is_the_deed_and_validation_state_derives_from_it(
    request: pytest.FixtureRequest,
) -> None:
    async with ScadaLiveTest(request=request) as tst:
        app = tst.child1_app
        deed = app.ta_deed
        assert isinstance(deed, TaDeed)
        assert deed.TaId == app.hardware_layout.terminal_asset_g_node_id
        assert app.validation_state == deed.ValidationState
        assert app.validation_state != TaValidationState.UnValidated

        remove_deed()
        assert app.ta_deed is None
        assert app.validation_state == TaValidationState.UnValidated


@pytest.mark.asyncio
async def test_a_deed_for_another_terminal_asset_is_no_deed(
    request: pytest.FixtureRequest,
) -> None:
    async with ScadaLiveTest(request=request) as tst:
        app = tst.child1_app
        other = deed_another_asset()
        assert app.deed_on_file == other
        assert app.ta_deed is None
        assert app.validation_state == TaValidationState.UnValidated


@pytest.mark.asyncio
async def test_announcements_with_a_deed_are_the_layout_and_that_deed(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Scada, "announce_at_first_broker_link", no_announcer)
    async with ScadaLiveTest(request=request) as tst:
        tst.start_child1()
        scada = tst.child1_app.scada
        sent = record_sends(monkeypatch, scada)
        scada.send_startup_announcements()
        assert [type(p) for p in sent] == [LayoutLite, TaDeed, HouseOperatingStatus, ScadaCommit]
        assert sent[0].FromGNodeAlias == scada.layout.scada_g_node_alias
        assert sent[1] == tst.child1_app.ta_deed


@pytest.mark.asyncio
async def test_the_commit_announced_is_the_checkouts_head(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Scada, "announce_at_first_broker_link", no_announcer)
    async with ScadaLiveTest(request=request) as tst:
        tst.start_child1()
        scada = tst.child1_app.scada
        sent = record_sends(monkeypatch, scada)
        scada.send_startup_announcements()
        commit = sent[3]
        assert isinstance(commit, ScadaCommit)
        assert commit.ScadaAlias == scada.layout.scada_g_node_alias
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=SCADA_REPO_ROOT, capture_output=True, text=True
        ).stdout.strip()
        assert commit.GitCommit.removesuffix("-dirty") == head


@pytest.mark.asyncio
async def test_no_checkout_means_no_commit_announcement(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert git_commit_of(tmp_path) is None
    monkeypatch.setattr(actors.scada, "SCADA_REPO_ROOT", tmp_path)
    monkeypatch.setattr(Scada, "announce_at_first_broker_link", no_announcer)
    async with ScadaLiveTest(request=request) as tst:
        tst.start_child1()
        scada = tst.child1_app.scada
        sent = record_sends(monkeypatch, scada)
        logged: list[str] = []
        monkeypatch.setattr(scada, "log", logged.append)
        scada.send_startup_announcements()
        assert [type(p) for p in sent] == [LayoutLite, TaDeed, HouseOperatingStatus]
        assert [note for note in logged if note.startswith("No gw.scada.commit")]


def test_git_commit_of_reads_head_and_marks_a_dirty_tree(tmp_path: Path) -> None:
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(tmp_path), "PATH": "/usr/bin:/bin",
    }
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=env)
    (tmp_path / "a").write_text("1")
    subprocess.run(["git", "add", "a"], cwd=tmp_path, check=True, env=env)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "a"],
                   cwd=tmp_path, check=True, env=env)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()
    assert git_commit_of(tmp_path) == head
    (tmp_path / "a").write_text("2")
    assert git_commit_of(tmp_path) == f"{head}-dirty"


@pytest.mark.asyncio
async def test_announcements_with_no_deed_are_the_layout_and_one_warning(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    remove_deed()
    monkeypatch.setattr(Scada, "announce_at_first_broker_link", no_announcer)
    async with ScadaLiveTest(request=request) as tst:
        tst.start_child1()
        scada = tst.child1_app.scada
        sent = record_sends(monkeypatch, scada)
        logged: list[str] = []
        monkeypatch.setattr(scada, "log", logged.append)
        scada.send_startup_announcements()
        assert [type(p) for p in sent] == [LayoutLite, Glitch, HouseOperatingStatus, ScadaCommit]
        assert [note for note in logged if note.startswith("Warning Glitch: no-ta-deed")]
        glitch = sent[1]
        assert isinstance(glitch, Glitch)
        assert glitch.Type == LogLevel.Warning
        assert glitch.Summary == "no-ta-deed"
        assert glitch.FromGNodeAlias == scada.layout.scada_g_node_alias


@pytest.mark.asyncio
async def test_announcements_with_another_assets_deed_are_the_layout_and_one_warning(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = deed_another_asset()
    monkeypatch.setattr(Scada, "announce_at_first_broker_link", no_announcer)
    async with ScadaLiveTest(request=request) as tst:
        tst.start_child1()
        scada = tst.child1_app.scada
        sent = record_sends(monkeypatch, scada)
        logged: list[str] = []
        monkeypatch.setattr(scada, "log", logged.append)
        scada.send_startup_announcements()
        assert [type(p) for p in sent] == [LayoutLite, Glitch, HouseOperatingStatus, ScadaCommit]
        assert [note for note in logged if note.startswith("Warning Glitch: ta-deed-wrong-asset")]
        glitch = sent[1]
        assert isinstance(glitch, Glitch)
        assert glitch.Type == LogLevel.Warning
        assert glitch.Summary == "ta-deed-wrong-asset"
        assert other.TaId in glitch.Details
        assert scada.layout.terminal_asset_g_node_id in glitch.Details
        status = sent[2]
        assert isinstance(status, HouseOperatingStatus)
        assert status.ValidationState == TaValidationState.UnValidated


@pytest.mark.asyncio
async def test_announces_once_with_no_ltn_and_not_again_on_activation(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    link_active_at_call: list[bool] = []

    def count_call(self: Scada) -> None:
        link_active_at_call.append(tst.child_to_parent_link.active())

    monkeypatch.setattr(Scada, "send_startup_announcements", count_call)
    monkeypatch.setattr(Scada, "STARTUP_ANNOUNCE_POLL_S", 0.01)

    async with ScadaLiveTest(request=request) as tst:
        tst.start_child1()
        await tst.await_for(
            lambda: len(link_active_at_call) == 1,
            "ERROR waiting for the startup announcements with no LTN",
        )
        # Sent on the broker link alone: no peer had activated it.
        assert link_active_at_call == [False]

        tst.start_parent()
        await tst.await_for(
            lambda: tst.child_to_parent_link.active(),
            "ERROR waiting for scada to ltn link",
        )
        await asyncio.sleep(0.2)
        assert len(link_active_at_call) == 1


@pytest.mark.asyncio
async def test_nothing_is_announced_until_the_link_is_send_capable(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    send_capable = False

    monkeypatch.setattr(Scada, "send_startup_announcements", lambda self: calls.append(1))
    monkeypatch.setattr(Scada, "STARTUP_ANNOUNCE_POLL_S", 0.01)
    monkeypatch.setattr(ScadaApp, "upstream_is_send_capable", lambda self: send_capable)

    async with ScadaLiveTest(request=request) as tst:
        tst.start_child1()
        await asyncio.sleep(0.3)
        assert calls == []

        send_capable = True
        await tst.await_for(
            lambda: calls == [1],
            "ERROR waiting for the startup announcements",
        )
