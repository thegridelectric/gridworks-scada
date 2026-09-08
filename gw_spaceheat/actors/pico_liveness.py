"""Whether a pico-fed actor's pico is still posting, and when to say it
is not. One home for the three HTTP-fed actors (tank module, BTU meter,
flow module), which each kept their own copy of this bookkeeping and
drifted: the tank module's report rate limit compared a timestamp to a
duration and its threshold was one post period, so a single slow post
read as missing and, once missing, was reported every loop tick.

A false missing report is expensive: the pico-cycler answers it by
power-cycling the shared VDC bus, so every pico on the house reboots and
rejoins wifi as a herd (the 2026-08 pico gap analysis).

Pure: every method takes the current time, so a test drives it with no
clock tricks."""

import time
from typing import Optional


class PicoLiveness:
    """A pico is missing after MISSING_MULTIPLE expected post periods of
    silence. The first missing report is due as soon as that threshold is
    crossed; while the silence lasts, one more report is due every
    REPORT_PERIOD_S; a post resets both."""

    MISSING_MULTIPLE = 2.5
    REPORT_PERIOD_S = 60

    def __init__(self, expected_post_s: float, now: Optional[float] = None) -> None:
        if expected_post_s <= 0:
            raise ValueError(f"expected_post_s must be positive, got {expected_post_s}")
        self.expected_post_s = expected_post_s
        self.last_heard = time.time() if now is None else now
        self.last_report: Optional[float] = None

    @property
    def flatline_seconds(self) -> float:
        return self.expected_post_s * self.MISSING_MULTIPLE

    def heard(self, now: float) -> None:
        self.last_heard = now
        self.last_report = None

    def missing(self, now: float) -> bool:
        return now - self.last_heard > self.flatline_seconds

    def report_due(self, now: float) -> bool:
        """True when a missing report should go out now; records it."""
        if not self.missing(now):
            return False
        if self.last_report is not None and now - self.last_report < self.REPORT_PERIOD_S:
            return False
        self.last_report = now
        return True
