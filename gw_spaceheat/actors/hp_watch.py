"""hp-watch: the heat pump as the scada senses it."""

import time

from gwproto.message import Message
from gwsproto.enums import SpruceHackHpState
from gwsproto.named_types import ChannelFlatlined, SingleMachineState, SingleReading
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from result import Ok, Result

from actors.hp_boss.sensing import HP_TRAITS, HpTraits
from actors.in_process_messages import ChannelSubscribe
from actors.sh_node_actor import ShNodeActor
from scada_app_interface import ScadaAppInterface

HELD_ON_S = 600  # HpDetectedOn with every read between the lines this long is a stopped unit
HP_WATCH_HELD_ON = "hp-watch-held-on"


class HpWatch(ShNodeActor):
    """The actor at the hp-watch node, where the heat pump's sensed running
    state is reported as a machine state. It runs the threshold machine on
    hp-odu power as the scada forwards it: HpDetectedOn on a read above the
    heat pump's on line, HpDetectedOff on a read below its off line, held in
    between, and Unknown at start and whenever the channel flatlines. A
    read between the lines while Unknown is HpDetectedOff: running the pump
    when the system is not hot destratifies the buffer.

    The lines bracket a band the unit only passes through, so HpDetectedOn
    with every read between them for HELD_ON_S means the unit has stopped
    and its standby draw sits above the off line: the secondary pump is
    running between cycles. The watch says so with one Warning glitch per
    such spell and leaves the state alone."""

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        hp_odu = self.required_node(HSNN.hp_odu).component
        if hp_odu is None:
            raise ValueError(f"{HSNN.hp_odu} has no component; cannot read its device type")
        self.traits: HpTraits = HP_TRAITS[hp_odu.gt.DeviceType]
        self.state: SpruceHackHpState = SpruceHackHpState.Unknown
        # Read time of the first between-read since the last read above the
        # on line, while HpDetectedOn; None otherwise.
        self.between_since_s: float | None = None
        self.held_on_reported: bool = False

    def start(self) -> None:
        self._send_to(self.primary_scada, ChannelSubscribe(ChannelName=HCN.hp_odu_pwr))
        self.report_state()

    def stop(self) -> None:
        ...

    async def join(self) -> None:
        ...

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        payload = message.Payload
        match payload:
            case SingleReading():
                if payload.ChannelName == HCN.hp_odu_pwr:
                    self.process_power(payload.Value, payload.ScadaReadTimeUnixMs / 1000)
            case ChannelFlatlined():
                if payload.Channel.Name == HCN.hp_odu_pwr:
                    self.move_to(SpruceHackHpState.Unknown)
            case _:
                self.log(f"{self.name} received unexpected message: {message.Header}")
        return Ok(True)

    def process_power(self, watts: int, read_s: float) -> None:
        if watts > self.traits.on_above_w:
            self.move_to(SpruceHackHpState.HpDetectedOn)
            self.between_since_s = None
            self.held_on_reported = False
        elif watts < self.traits.off_below_w or self.state == SpruceHackHpState.Unknown:
            self.move_to(SpruceHackHpState.HpDetectedOff)
        elif self.state == SpruceHackHpState.HpDetectedOn:
            self.watch_held_on(watts, read_s)

    def watch_held_on(self, watts: int, read_s: float) -> None:
        """A between-read while HpDetectedOn: the start of a possible held
        On, or its HELD_ON_S mark, reported once per spell."""
        if self.between_since_s is None:
            self.between_since_s = read_s
            return
        held_s = read_s - self.between_since_s
        if held_s < HELD_ON_S or self.held_on_reported:
            return
        self.held_on_reported = True
        self.send_warning(
            HP_WATCH_HELD_ON,
            f"HpDetectedOn held {int(held_s)} s with {HCN.hp_odu_pwr} between the "
            f"lines ({watts} W; off below {self.traits.off_below_w} W, on above "
            f"{self.traits.on_above_w} W): the unit has stopped and its standby "
            "draw is above the off line, so the secondary pump runs between cycles",
        )

    def move_to(self, state: SpruceHackHpState) -> None:
        if state == self.state:
            return
        self.log(f"{self.state} -> {state}")
        self.state = state
        self.between_since_s = None
        self.held_on_reported = False
        self.report_state()

    def report_state(self) -> None:
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=SpruceHackHpState.enum_name(),
                State=self.state,
                UnixMs=int(time.time() * 1000),
            ),
        )
