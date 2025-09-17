"""
Tests for enum log.level.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import LogLevel


def test_log_level() -> None:
    assert set(LogLevel.values()) == {
        "Critical",
        "Error",
        "Warning",
        "Info",
        "Debug",
        "Trace",
    }

    assert LogLevel.default() == LogLevel.Info
    assert LogLevel.enum_name() == "log.level"
    assert LogLevel.enum_version() == "000"
