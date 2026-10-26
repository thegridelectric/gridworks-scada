"""Once-per-interval gating for a glitch whose condition would otherwise
repeat on every post, read or poll."""
import time

REPEAT_GLITCH_S = 24 * 3600  # a standing condition is reported once a day per key


class GlitchLimit:
    """When each key's glitch last went out."""

    def __init__(self, interval_s: float) -> None:
        self.interval_s = interval_s
        self.sent_s: dict[str, float] = {}

    def due(self, key: str) -> bool:
        """True if the key's glitch may go now, and records that it did."""
        now = time.time()
        last = self.sent_s.get(key)
        if last is not None and now - last < self.interval_s:
            return False
        self.sent_s[key] = now
        return True
