"""One 0-10V output as an actuator: a leaf of the command tree that takes
AnalogDispatch from its boss and drives a level."""

import asyncio
import time
from typing import Sequence

from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto.message import Message
from result import Ok, Result

from actors.sh_node_actor import ShNodeActor
from plant import Heard, LevelDrive, Said, Streaks
from scada_app_interface import ScadaAppInterface
from sema_to_dc import zero_ten_power_on_volts_times_ten

from gwsproto.data_classes.components import I2cDacOutputComponent
from gwsproto.data_classes.sh_node import ShNode
from actors import command_reply
from gwsproto.enums import ScadaCmdRefusalReason
from gwsproto.named_types import (
    ActuatorsReady,
    AnalogDispatch,
    DacOutputConfig,
    SingleReading,
)

# AnalogDispatch.Value for a 0-10V output is volts times ten, 0-100 — the
# unit the VoltsTimesTen channel reports.
VOLTS_TIMES_TEN_MAX = 100


class ZeroTenOutputer(ShNodeActor):
    """
    One 0-10 V output, driven through the node's level drive. The power-on
    level comes from the ops word (zero.ten.power.on). The output is
    prepared once after boot, retried each heartbeat until it is ready.
    Then the target level — the power-on level until the first dispatch,
    the last commanded level after — is set again every heartbeat and on
    every dispatch. A set that took reports the level the output holds on
    the output's channel.
    """

    HEARTBEAT_S = 60

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self.stop_requested = False
        # the output's one-time step after boot is done; retried each
        # heartbeat until it is
        self.output_ready = False
        self.streaks = Streaks()
        self.wake = asyncio.Event()

        component = self.node.component
        if not isinstance(component, I2cDacOutputComponent):
            raise ValueError(
                f"{self.name} expected I2cDacOutputComponent, got {type(component)}"
            )
        self.dac: I2cDacOutputComponent = component
        config = component.gt.ConfigList[0]
        if config.ActorName != self.name:
            raise ValueError(
                f"{self.name}: component config names actor {config.ActorName}"
            )
        self.config: DacOutputConfig = config
        self.power_on_level: int = zero_ten_power_on_volts_times_ten(self.ops, self.name)
        # The level the heartbeat holds: the ops word's power-on level until
        # the first dispatch, the last commanded level after.
        self.target_level: int = self.power_on_level
        self.drive = self.my_device(LevelDrive)

    # ---- dispatch ----

    def process_analog_dispatch(self, from_node: ShNode, dispatch: AnalogDispatch) -> None:
        """from_node is who put the message on the wire (the transport
        header's source); the dispatch's FromHandle is who the sender claims
        to be in the command tree. The two must agree before anything else
        is looked at."""
        if dispatch.FromHandle != from_node.handle:
            self.send_warning(
                "bad_sender",
                f"{from_node.name} (handle {from_node.handle}) sent a dispatch claiming "
                f"FromHandle {dispatch.FromHandle}. Ignoring!",
            )
            return
        if dispatch.ToHandle != self.node.handle:
            self.log(f"Ignoring dispatch {dispatch} - ToHandle is not {self.node.handle}!")
            self._send_to(
                from_node,
                command_reply.nack(
                    self.node.handle, dispatch.FromHandle, dispatch.TriggerId,
                    ScadaCmdRefusalReason.NotMyBoss,
                ),
            )
            return
        if dispatch.AboutName != self.node.name:
            self.log(f"Ignoring dispatch {dispatch} -- expect AboutName to be about me")
        if dispatch.Value not in range(VOLTS_TIMES_TEN_MAX + 1):
            self.log(
                f"Refusing dispatch {dispatch} - value out of range. "
                f"Should be 0-{VOLTS_TIMES_TEN_MAX}"
            )
            self._send_to(
                from_node,
                command_reply.nack(
                    self.node.handle, dispatch.FromHandle, dispatch.TriggerId,
                    ScadaCmdRefusalReason.OutOfRange,
                ),
            )
            return
        self._send_to(
            from_node,
            command_reply.ack(self.node.handle, dispatch.FromHandle, dispatch.TriggerId),
        )
        self.target_level = dispatch.Value
        self.log(f"Dispatch from {dispatch.FromHandle}: volts x10 {dispatch.Value}")
        self.wake.set()

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        payload = message.Payload
        if isinstance(payload, AnalogDispatch):
            from_node = self.layout.node(message.Header.Src, None)
            if from_node is None:
                self.log(f"Ignoring {payload.TypeName} from {message.Header.Src} - not in layout")
                return Ok(False)
            try:
                self.process_analog_dispatch(from_node, payload)
            except Exception as e:
                self.log(f"Trouble with process_analog_dispatch: {e}")
            return Ok(True)
        if self.drive.hears(payload) != Heard.NotMine:
            return Ok(True)
        self.log(f"Got unexpected {payload.TypeName} from {message.Header.Src}")
        return Ok(True)

    def report(self, about: str, said: tuple[Said, ...]) -> None:
        """One Glitch for each thing the drive said that is new: a streak
        of the same failure is one Glitch, until it stops."""
        for one in self.streaks.fresh(about, said):
            self.send_warning(summary=one.summary, details=f"{self.name}: {one.details}")

    async def assert_target(self) -> None:
        """Set the target level and report the level held; retried every
        heartbeat."""
        level_set = await self.drive.set(self.target_level)
        self.report("set", level_set.said)
        if level_set.held is None:
            return
        self._send_to(
            self.primary_scada,
            SingleReading(
                ChannelName=self.config.ChannelName,
                Value=level_set.held,
                ScadaReadTimeUnixMs=int(time.time() * 1000),
            ),
        )

    async def prepare_output(self) -> bool:
        prepared = await self.drive.prepare(self.power_on_level)
        self.report("prepare", prepared.said)
        if prepared.note:
            self.log(f"{self.name}: {prepared.note}")
        return prepared.ready

    # ---- lifecycle ----

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.HEARTBEAT_S * 2)]

    def start(self) -> None:
        self.services.add_task(
            asyncio.create_task(self.main_loop(), name=f"{self.name}-main")
        )
        self._send_to(self.primary_scada, ActuatorsReady())

    async def main_loop(self) -> None:
        """Watchdog pat + level enforcement each pass: the output's step
        after boot (retried until it completes once: a bus refuses ops
        until its init guard finishes), then the target set. A dispatch
        wakes the loop early, so sets serialize in this one task."""
        while not self.stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            self.wake.clear()
            if not self.output_ready:
                self.output_ready = await self.prepare_output()
            await self.assert_target()
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=self.HEARTBEAT_S)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self.stop_requested = True
        self.wake.set()

    async def join(self) -> None: ...
