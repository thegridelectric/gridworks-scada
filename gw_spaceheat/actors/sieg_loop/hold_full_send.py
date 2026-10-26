"""HoldFullSend: the valve goes to full send once the actuators are ready
and then only answers commands. No inputs, no control state; the heat pump
behaves as if there were no loop."""

from gwsproto.enums import HpBossState

from actors.sieg_loop.strategy import SiegStrategy


class HoldFullSend(SiegStrategy):
    def on_actuators_ready(self) -> None:
        if self.loop.automatic:
            self.loop.valve.move_to_full_send()

    def on_hp_boss_state(self, state: HpBossState) -> None:
        ...

    def tick(self) -> None:
        ...

    def resume(self) -> None:
        self.loop.valve.move_to_full_send()
