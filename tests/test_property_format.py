"""Tests handle.name and spaceheat.name property formats."""

import pytest

from gwsproto.property_format import is_handle_name, is_spaceheat_name


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
