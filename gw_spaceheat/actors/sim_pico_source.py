from typing import Callable, Generic, Optional, TypeVar

from gwsproto.enums import RelayClosedOrOpen
from gwsproto.named_types import MicroVolts, MultichannelSnapshot

SIM_PICO_TICK_S = 1

PicoReadingT = TypeVar("PicoReadingT", MicroVolts, MultichannelSnapshot)


class SimPicoSource(Generic[PicoReadingT]):
    """A simulated pico: a liveness stand-in, not a sensor.

    How it operates. The owning pico actor ticks it once a second
    (SIM_PICO_TICK_S) and posts whatever it returns to itself, on the same
    path the web handler uses for a real pico's HTTP post. Each tick:

    - if the pico is dead and a reboot is due, it boots (the boot clock
      restarts);
    - if alive for SimLifeS since its boot, it dies (goes silent);
    - if alive and a capture period has passed since its last post, it
      returns its reading; otherwise nothing.

    Power follows the vdc relay: the actor feeds it every new state of that
    relay from the scada's latest machine states. An open kills it at once;
    the close that follows an open schedules a boot SimRebootS later. So a
    pico-cycler cycle (open, wait, close) revives it after SimRebootS, the
    way a real board rejoins wifi after a power cycle.

    A post can drop part of the reading: while omitted_names is not empty
    the source posts what the actor's `without` makes of the reading and
    those names, as a pico does that keeps posting with one sensor gone.

    What it is not. The reading is the one fixed payload the actor built
    it with, whose values never move and know nothing of the plant; the death
    is on a fixed schedule, not a failure model; a reboot always succeeds,
    so zombies never arise on their own (SimRebootS absent is the only
    zombie path, a pico that stays dead); and nothing crosses HTTP, so the
    real ingress path is not exercised. SimLifeS and SimRebootS come from
    the layout's sim component (tlayouts emits 120 s and 20 s so a flatline
    and a cycle fit inside a five-minute run); either absent means absent:
    no scheduled death, no reboot. Pure: every method takes the current
    time, so a test drives it with no clock tricks."""

    def __init__(
        self,
        reading: PicoReadingT,
        without: Callable[[PicoReadingT, set[str]], PicoReadingT],
        capture_period_s: int,
        life_s: Optional[int],
        reboot_s: Optional[int],
        booted_at: float,
    ) -> None:
        self.reading = reading
        self.without = without
        self.omitted_names: set[str] = set()
        self.capture_period_s = capture_period_s
        self.life_s = life_s
        self.reboot_s = reboot_s
        self.alive = True
        self.booted_at = booted_at
        self.last_post: Optional[float] = None
        self.relay_open_seen = False
        self.reboot_at: Optional[float] = None

    def relay_state(self, state: RelayClosedOrOpen, now: float) -> None:
        """Feed a vdc relay state change. Open cuts the pico's power; the
        close that follows schedules a reboot if SimRebootS is set."""
        if state == RelayClosedOrOpen.RelayOpen:
            self.alive = False
            self.reboot_at = None
            self.relay_open_seen = True
        elif self.relay_open_seen:
            self.relay_open_seen = False
            if self.reboot_s is not None:
                self.reboot_at = now + self.reboot_s

    def tick(self, now: float) -> Optional[PicoReadingT]:
        """Advance to now; the reading to post, if one is due."""
        if not self.alive:
            if self.reboot_at is None or now < self.reboot_at:
                return None
            self.alive = True
            self.booted_at = now
            self.last_post = None
            self.reboot_at = None
        if self.life_s is not None and now - self.booted_at >= self.life_s:
            self.alive = False
            return None
        if self.last_post is not None and now - self.last_post < self.capture_period_s:
            return None
        self.last_post = now
        if self.omitted_names:
            return self.without(self.reading, self.omitted_names)
        return self.reading
