import asyncio
from typing import Any, Optional, Sequence

from gwproto.message import Message
from gwproactor import MonitoredName
from result import Result

from actors.sh_node_actor import ShNodeActor
from actors.sieg_loop.fallback import SiegLoopFallback
from actors.sieg_loop.pid import SiegLoopPid
from gwsproto.data_classes.house_0_names import H0CN, H0N
from gwsproto.enums import ActorClass, SiegLoopMode
from scada_app_interface import ScadaAppInterface


class SiegLoop(ShNodeActor):
    HEALTH_CHECK_SECONDS = 60

    _IMPL_BY_MODE = {
        SiegLoopMode.PidControl: SiegLoopPid,
        SiegLoopMode.Fallback: SiegLoopFallback,
    }

    _SHARED_RUNTIME_ATTRS = (
        "keep_seconds",
        "actuators_ready",
        "hp_boss_state",
        "hp_turned_off_time",
        "target_lwt_from_boss",
        "control_interval_seconds",
        "t1",
        "t2",
    )

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        node = services.hardware_layout.node(name)
        if node is None:
            raise Exception("Missing the SiegLoop node!")
        if node.ActorClass != ActorClass.SiegLoop:
            raise Exception("SiegLoop node should have ActorClass SiegLoop!")

        self._impl: ShNodeActor | None = None
        self._mode: SiegLoopMode | None = None
        self._started = False
        self._stop_requested = False
        self._health_check_task: asyncio.Task | None = None

        self._switch_to_mode(
            self.settings.sieg_loop_default_mode,
            reason="Default SiegLoop strategy from SCADA settings",
            emit_info=False,
        )

    @property
    def mode(self) -> SiegLoopMode:
        if self._mode is None:
            raise Exception("SiegLoop mode has not been initialized")
        return self._mode

    @property
    def active_implementation(self) -> ShNodeActor:
        if self._impl is None:
            raise Exception("SiegLoop implementation has not been initialized")
        return self._impl

    def switch_to_fallback(self, reason: str) -> None:
        self._switch_to_mode(SiegLoopMode.Fallback, reason=reason)

    def switch_to_pid(self, reason: str) -> None:
        healthy, health_reason = self.evaluate_strategy_health()
        if not healthy:
            summary = "SiegLoop PID strategy not started"
            details = f"{reason}\n{health_reason}"
            self.log(f"{summary}: {details}")
            self.send_info(summary, details)
            return
        self._switch_to_mode(SiegLoopMode.PidControl, reason=reason)

    def evaluate_strategy_health(self) -> tuple[bool, str]:
        missing = []
        for channel_name in self._pid_required_channels():
            available, reason = self._check_channel_availability(channel_name)
            if not available:
                missing.append(f"{channel_name}: {reason}")

        if H0N.store_charge_discharge_relay not in self.data.latest_machine_state:
            missing.append(f"{H0N.store_charge_discharge_relay}: no relay state")

        if missing:
            details = "Missing PID input data:\n" + "\n".join(f"- {x}" for x in missing)
            return False, details
        return True, "PID input data present"

    def _pid_required_channels(self) -> list[str]:
        channels = [
            H0CN.hp_ewt,
            H0CN.hp_lwt,
            H0CN.hp_odu_pwr,
            H0CN.hp_idu_pwr,
            H0CN.sieg_cold,
        ]
        channels.extend(sorted(self.h0cn.buffer.effective))
        for tank_idx in sorted(self.h0cn.tank):
            channels.extend(sorted(self.h0cn.tank[tank_idx].effective))
        return list(dict.fromkeys(channels))

    def _check_channel_availability(self, channel_name: str) -> Optional[str]:
        channel = (
            self.layout.channel(channel_name)
            or self.layout.derived_channels.get(channel_name)
        )
        if channel is None:
            return False, "not in hardware layout"
        if not self.data.channel_has_value(channel_name):
            return False, "no latest value"
        if self.data.flatlined(channel):
            return False, "flatlined"
        return True, None

    def _switch_to_mode(
        self,
        mode: SiegLoopMode,
        *,
        reason: str,
        emit_info: bool = True,
    ) -> None:
        if mode not in self._IMPL_BY_MODE:
            raise ValueError(f"Unsupported SiegLoop mode {mode}")
        if self._mode == mode:
            self.log(f"SiegLoop already using {mode}; reason: {reason}")
            return

        old_mode = self._mode
        old_impl = self._impl
        if old_impl is not None:
            old_impl.stop()

        impl_class = self._IMPL_BY_MODE[mode]
        new_impl = impl_class(self.name, self.services)
        self._copy_runtime_state(old_impl, new_impl)
        self._impl = new_impl
        self._mode = mode

        if self._started:
            new_impl.start()

        old_label = old_mode.value if old_mode is not None else "None"
        summary = f"SiegLoop strategy changed: {old_label} -> {mode.value}"
        details = (
            f"Reason: {reason}\n"
            f"Implementation: {impl_class.__module__}.{impl_class.__name__}"
        )
        self.log(f"{summary}. {details}")
        if emit_info:
            self.send_info(summary, details)

    def _copy_runtime_state(
        self,
        old_impl: ShNodeActor | None,
        new_impl: ShNodeActor,
    ) -> None:
        if old_impl is None:
            return
        for attr in self._SHARED_RUNTIME_ATTRS:
            if hasattr(old_impl, attr) and hasattr(new_impl, attr):
                setattr(new_impl, attr, getattr(old_impl, attr))

    async def _health_check_loop(self) -> None:
        while not self._stop_requested:
            await asyncio.sleep(self.HEALTH_CHECK_SECONDS)
            try:
                if self._mode == SiegLoopMode.Fallback:
                    continue
                healthy, reason = self.evaluate_strategy_health()
                if not healthy:
                    self.switch_to_fallback(reason)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.log(f"Trouble evaluating SiegLoop strategy health: {e}")

    def process_message(self, message: Message[Any]) -> Result[bool, Exception]:
        return self.active_implementation.process_message(message)

    def start(self) -> None:
        self._stop_requested = False
        self._started = True
        self.active_implementation.start()
        self._health_check_task = asyncio.create_task(
            self._health_check_loop(),
            name="Sieg Loop Strategy Health Check",
        )
        self.services.add_task(self._health_check_task)

    def stop(self) -> None:
        self._stop_requested = True
        self._started = False
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
        self.active_implementation.stop()

    async def join(self) -> None:
        if self._health_check_task is not None:
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                ...
        await self.active_implementation.join()

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return self.active_implementation.monitored_names
