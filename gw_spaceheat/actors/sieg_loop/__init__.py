"""sieg-loop, the Siegenthaler-loop actor: one valve, driven by the
strategy the ops word selects. The facade owns what every strategy shares,
the valve and its state report, the tick, the watchdog pat and the hp-boss
subscription; the strategy decides what the valve does."""

import asyncio
from typing import Any, Sequence

from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto.message import Message
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import HpBossState, SiegLoopStrategy
from gwsproto.named_types import ActuatorsReady, SingleMachineState
from result import Ok, Result

from actors.hydronic.house0 import House0Hydronic
from actors.sieg_loop.hold_full_send import HoldFullSend
from actors.sieg_loop.strat_protect import SiegControlEvent, SiegControlState, StratProtect
from actors.sieg_loop.strategy import SiegLoopReady, SiegStrategy, selected_strategy
from actors.sieg_loop.valve import SiegValve, SiegValveEvent, SiegValveState
from scada_app_interface import ScadaAppInterface

__all__ = [
    "HoldFullSend",
    "SiegControlEvent",
    "SiegControlState",
    "SiegLoop",
    "SiegLoopReady",
    "SiegStrategy",
    "SiegValve",
    "SiegValveEvent",
    "SiegValveState",
    "StratProtect",
    "selected_strategy",
]


class SiegLoop(House0Hydronic):
    """Base class: House0Hydronic carries the relay choreography for relays
    14 and 15 (change_to_hp_keep_more / _less, sieg_valve_active / _hold)
    and the loop's reads (lwt, ewt, lift_f, total_hp_pwr_w). A fall-2026
    layout has a Siegenthaler loop without the House0 hydronic set, so the
    choreography is not House0's; the base class changes with that layout.
    """

    CONTROL_INTERVAL_S = 30
    PAT_INTERVAL_S = 5 * 60

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self.stop_requested = False
        self.actuators_ready = False
        self.since_last_pat_s = self.PAT_INTERVAL_S
        self.valve = SiegValve(self)
        strategy = selected_strategy(self.ops)
        if strategy is SiegLoopStrategy.HoldFullSend:
            self.strategy: SiegStrategy = HoldFullSend(self)
        elif strategy is SiegLoopStrategy.StratProtect:
            self.strategy = StratProtect(self)
        else:
            raise ValueError(
                f"{self.name} cannot run SiegLoopStrategy {strategy}: only "
                f"{SiegLoopStrategy.HoldFullSend} and {SiegLoopStrategy.StratProtect} are built"
            )
        self.log(f"Running {type(self.strategy).__name__}")

    # --------------------------------------
    # Main loop
    # --------------------------------------

    async def main(self) -> None:
        while not self.stop_requested:
            self.strategy.tick()
            if self.since_last_pat_s >= self.PAT_INTERVAL_S:
                self.since_last_pat_s = 0
                self._send(PatInternalWatchdogMessage(src=self.name))
            self.since_last_pat_s += self.CONTROL_INTERVAL_S
            await self.services.clock.sleep(self.CONTROL_INTERVAL_S)

    # --------------------------------------
    # Message processing
    # --------------------------------------

    def process_message(self, message: Message[Any]) -> Result[bool, Exception]:
        from_node = self.layout.node(message.Header.Src, None)
        if from_node is None:
            return Ok(False)
        payload = message.Payload
        match payload:
            case ActuatorsReady():
                self.actuators_ready = True
                self.strategy.on_actuators_ready()
            case SingleMachineState():
                self.process_single_machine_state(from_node, payload)
            case _:
                self.log(f"{self.name} received unexpected message: {message.Header}")
        return Ok(True)

    def process_single_machine_state(self, from_node: ShNode, payload: SingleMachineState) -> None:
        if payload.StateEnum != HpBossState.enum_name():
            raise Exception(
                f"The StateEnum {payload.StateEnum} is not a HpBossState enum: {HpBossState.enum_name()}"
            )
        if from_node != self.hp_boss:
            raise Exception("Not expecting single machine state messages except from HpBoss")
        self.log(f"Just received state {payload.State} from HpBoss")
        self.strategy.on_hp_boss_state(HpBossState(payload.State))

    def report_valve_state(self, cause: SiegValveEvent) -> None:
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=SiegValveState.enum_name(),
                State=self.valve.valve_state,
                UnixMs=self.services.clock.now_ms(),
                Cause=cause,
            ),
        )

    # --------------------------------------
    # Required methods and properties
    # --------------------------------------

    def start(self) -> None:
        self.services.add_task(asyncio.create_task(self.main(), name="Sieg Loop Synchronous Report"))

    def stop(self) -> None:
        self.stop_requested = True

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""
        ...

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, 400)]
