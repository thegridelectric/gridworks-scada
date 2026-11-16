"""StratProtect keeps the buffer tank stratified while the heat pump is
off and the primary pump runs: the Siegenthaler valve stays at keep while
the heat pump is off or starting cold, opens toward send once the loop is
hot, and goes to full send when the loop cannot tell what a running heat
pump is doing or when the outdoor unit draws running power after an off
(a heat pump honours an off on its own clock: the Ecodan runs about six
minutes from a compressor start). Its inputs are hp-boss's reported state
and the loop's own leaving and entering water temperatures and heat pump
power. The valve's position is unknown at boot, so the first move is a
full run to a stop."""

from enum import auto
from typing import Optional

from gwsproto.enums import HpBossState
from gwsproto.enums.gw_str_enum import GwStrEnum
from transitions import Machine

from actors.sieg_loop.strategy import SiegLoopReady, SiegStrategy


class SiegControlState(GwStrEnum):
    Initializing = auto()
    Blind = auto()
    HpOff = auto()
    HpStartingUp = auto()
    HpHasLift = auto()

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.sieg.control.state"


class SiegControlEvent(GwStrEnum):
    DoneInitializingBlind = auto()
    DoneInitializingHpOn = auto()
    DoneInitializingHpOff = auto()
    DoneInitializingHpStartingUp = auto()
    BecameBlind = auto()
    NoLongerBlindHpOn = auto()
    NoLongerBlindHpOff = auto()
    NoLongerBlindHpStartingUp = auto()
    HpTurnsOff = auto()
    HpTurnsOn = auto()
    HpStartUpDone = auto()


class StratProtect(SiegStrategy):
    # The outdoor unit's draw above which the compressor is running.
    # Interim: a heat-pump fact spelled again here (the hp-boss sensing
    # surface, actors/hp_boss/sensing.py, holds the same draw by device
    # type) and not keyed by device type; it belongs there, read as the
    # unit's sensed state once it reports one.
    IDLE_POWER_W = 500

    transitions = [
        # Initializing
        {"trigger": "DoneInitializingBlind", "source": "Initializing", "dest": "Blind"},
        {"trigger": "DoneInitializingHpOn", "source": "Initializing", "dest": "HpHasLift"},
        {"trigger": "DoneInitializingHpOff", "source": "Initializing", "dest": "HpOff"},
        {"trigger": "DoneInitializingHpStartingUp", "source": "Initializing", "dest": "HpStartingUp"},

        # Turning off the heat pump
        {"trigger": "HpTurnsOff", "source": "HpStartingUp", "dest": "HpOff"},
        {"trigger": "HpTurnsOff", "source": "HpHasLift", "dest": "HpOff"},

        # Turning on the heat pump
        {"trigger": "HpTurnsOn", "source": "HpOff", "dest": "HpStartingUp"},

        # Reaching the end of the heat pump startup
        {"trigger": "HpStartUpDone", "source": "HpStartingUp", "dest": "HpHasLift"},

        # Going / leaving Blind state
        {"trigger": "BecameBlind", "source": "*", "dest": "Blind"},
        {"trigger": "NoLongerBlindHpOn", "source": "Blind", "dest": "HpHasLift"},
        {"trigger": "NoLongerBlindHpOff", "source": "Blind", "dest": "HpOff"},
        {"trigger": "NoLongerBlindHpStartingUp", "source": "Blind", "dest": "HpStartingUp"},
    ]

    def __init__(self, loop) -> None:
        super().__init__(loop)
        self.machine = Machine(
            model=self,
            states=SiegControlState.values(),
            transitions=self.transitions,
            initial=SiegControlState.Initializing,
            model_attribute="control_state",
            send_event=True,
        )
        self.control_state: SiegControlState = SiegControlState.Initializing
        # hp-boss's last reported state; None until it reports, and the
        # loop leaves Initializing only on a report.
        self.hp_boss_state: Optional[HpBossState] = None

    # --------------------------------------
    # Events from the facade
    # --------------------------------------

    def on_actuators_ready(self) -> None:
        self.engage_brain()

    def on_hp_boss_state(self, state: HpBossState) -> None:
        if (
            state == HpBossState.PreparingToTurnOn
            and self.hp_boss_state != HpBossState.PreparingToTurnOn
        ):
            self.loop.log("Sending SiegLoopReady to HpBoss")
            self.loop._send_to(self.loop.hp_boss, SiegLoopReady())
        self.hp_boss_state = state
        self.engage_brain()

    def tick(self) -> None:
        self.engage_brain()

    def resume(self) -> None:
        self.move_for(self.control_state)

    # --------------------------------------
    # Reads
    # --------------------------------------

    def heat_pump_is_running(self) -> bool:
        """The outdoor unit draws more than an idle heat pump does. The
        start opens the loop on this, conservatively early; a heat pump
        that never draws leaves the loop parked."""
        pwr = self.loop.hp_odu_pwr_w()
        return pwr is not None and pwr > self.IDLE_POWER_W

    def is_blind(self) -> bool:
        return self.blind_reason() is not None

    def blind_reason(self) -> Optional[str]:
        """With the heat pump off, the one thing to see is the outdoor unit
        still running; a missing reading changes nothing at keep. With it
        on, the loop is blind without its temperatures and power."""
        if self.hp_boss_state == HpBossState.HpOff:
            if self.heat_pump_is_running():
                return f"outdoor unit at {self.loop.hp_odu_pwr_w():.0f}W over {self.IDLE_POWER_W}W after off"
            return None
        if self.loop.lift_f() is None:
            return "no lift"
        if self.loop.total_hp_pwr_w() is None:
            return "no power"
        return None

    # --------------------------------------
    # Control state machine
    # --------------------------------------

    def engage_brain(self) -> None:
        self.loop.log(
            f"Engaging brain, control state is {self.control_state}, hp boss state is {self.hp_boss_state}"
        )
        if self.control_state == SiegControlState.Initializing:
            if not self.loop.actuators_ready:
                self.loop.log("Waiting for actuators to be ready to get out of Initializing state")
                return
            if self.hp_boss_state is None:
                self.loop.log("Waiting for hp-boss to report to get out of Initializing state")
                return
            if self.hp_boss_state == HpBossState.HpOff:
                self.trigger_control_event(SiegControlEvent.DoneInitializingHpOff)
            elif self.is_blind():
                self.loop.log(f"Blind: {self.blind_reason()}")
                self.trigger_control_event(SiegControlEvent.DoneInitializingBlind)
            elif self.hp_boss_state == HpBossState.PreparingToTurnOn:
                self.trigger_control_event(SiegControlEvent.DoneInitializingHpStartingUp)
            elif self.hp_boss_state == HpBossState.HpOn:
                if self.heat_pump_is_running():
                    self.trigger_control_event(SiegControlEvent.DoneInitializingHpOn)
                else:
                    self.trigger_control_event(SiegControlEvent.DoneInitializingHpStartingUp)

        # Get in/out of Blind state. Blind is full send: for a running heat
        # pump the loop cannot see, and for one still drawing running power
        # after an off, which rests at keep only once the draw stops.
        if self.control_state != SiegControlState.Blind and self.is_blind():
            self.loop.log(f"Blind: {self.blind_reason()}")
            self.trigger_control_event(SiegControlEvent.BecameBlind)
        elif self.control_state == SiegControlState.Blind and not self.is_blind():
            if self.hp_boss_state == HpBossState.HpOff:
                self.trigger_control_event(SiegControlEvent.NoLongerBlindHpOff)
            elif self.hp_boss_state == HpBossState.PreparingToTurnOn:
                self.trigger_control_event(SiegControlEvent.NoLongerBlindHpStartingUp)
            elif self.hp_boss_state == HpBossState.HpOn:
                if self.heat_pump_is_running():
                    self.trigger_control_event(SiegControlEvent.NoLongerBlindHpOn)
                else:
                    self.trigger_control_event(SiegControlEvent.NoLongerBlindHpStartingUp)

        if self.control_state == SiegControlState.Blind:
            return

        # Adapt state if not Blind
        if self.control_state != SiegControlState.HpOff and self.hp_boss_state == HpBossState.HpOff:
            self.trigger_control_event(SiegControlEvent.HpTurnsOff)
        elif (
            self.control_state not in [SiegControlState.HpStartingUp, SiegControlState.HpHasLift]
            and self.hp_boss_state in [HpBossState.PreparingToTurnOn, HpBossState.HpOn]
        ):
            self.trigger_control_event(SiegControlEvent.HpTurnsOn)
        elif self.control_state == SiegControlState.HpStartingUp:
            if self.heat_pump_is_running():
                self.trigger_control_event(SiegControlEvent.HpStartUpDone)

    def trigger_control_event(self, event: SiegControlEvent) -> None:
        orig_state = self.control_state
        getattr(self, event)(self)
        self.loop.log(f"{event}: {orig_state} -> {self.control_state}")
        if self.control_state == orig_state:
            self.loop.log(f"Warning: event {event} did not cause a change in control state")
            return
        if self.loop.automatic:
            self.move_for(self.control_state)

    def move_for(self, state: SiegControlState) -> None:
        """The valve posture the control state calls for. Until a run has
        reached a stop the valve's position is unknown, and every move is
        a full run to the stop on the posture's side."""
        valve = self.loop.valve
        if not valve.homed:
            if state in (SiegControlState.Blind, SiegControlState.HpHasLift):
                valve.full_run_to_send()
            else:
                valve.full_run_to_keep()
            return
        if state == SiegControlState.Blind:
            valve.move_to_full_send()
        elif state == SiegControlState.HpOff:
            # OFI (OPS-400): per heat pump. Maple (Mitsubishi, always-on
            # primary) needs full keep when off to protect stratification;
            # Beech (LG, timed primary) may want a different posture when off.
            valve.move_to_full_keep()
        elif state == SiegControlState.HpStartingUp:
            # Parked on the cusp: the first second of the open sends water.
            valve.move_to_just_keep()
        elif state == SiegControlState.HpHasLift:
            valve.move_to_full_send()
