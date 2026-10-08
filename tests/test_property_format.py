"""Tests git.commit, handle.name and spaceheat.name property formats."""

import pytest

from gwsproto.property_format import is_git_commit, is_handle_name, is_spaceheat_name


HEAD = "109d44041c2b3d4e5f60718293a4b5c6d7e8f901"


def test_git_commit_valid() -> None:
    assert is_git_commit(HEAD) == HEAD
    assert is_git_commit(HEAD + "-dirty") == HEAD + "-dirty"


@pytest.mark.parametrize("value", [HEAD[:7], HEAD.upper(), "unstamped", ""])
def test_git_commit_rejections(value: str) -> None:
    with pytest.raises(ValueError, match="Fails git.commit format"):
        is_git_commit(value)


def test_handle_name_valid() -> None:
    assert is_handle_name("auto.pico-cycler.relay1") == "auto.pico-cycler.relay1"


@pytest.mark.parametrize(
    "value",
    [
        "auto.9relay",
        "auto.-relay",
        "auto..relay",
    ],
)
def test_handle_name_rejections(value: str) -> None:
    with pytest.raises(ValueError, match="Fails HandleName format"):
        is_handle_name(value)


def test_spaceheat_name_valid() -> None:
    assert is_spaceheat_name("buffer-depth1") == "buffer-depth1"


def test_spaceheat_name_length_rejection() -> None:
    with pytest.raises(ValueError, match="exceeds maximum length of 64"):
        is_spaceheat_name("a" * 65)
