"""hp-sensor: the heat pump as the scada senses it."""

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


class HpSensor(ShNodeActor):
    """The actor at the hp-sensor node, where the heat pump's sensed running
    state is reported as a machine state. It runs the threshold machine on
    hp-odu power as the scada forwards it: HpDetectedOn on a read above the
    heat pump's on line, HpDetectedOff on a read below its off line, held in
    between, and Unknown at start and whenever the channel flatlines. A
    read between the lines while Unknown is HpDetectedOff: running the pump
    when the system is not hot destratifies the buffer."""

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        hp_odu = self.required_node(HSNN.hp_odu).component
        if hp_odu is None:
            raise ValueError(f"{HSNN.hp_odu} has no component; cannot read its device type")
        self.traits: HpTraits = HP_TRAITS[hp_odu.gt.DeviceType]
        self.state: SpruceHackHpState = SpruceHackHpState.Unknown

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
                    self.process_power(payload.Value)
            case ChannelFlatlined():
                if payload.Channel.Name == HCN.hp_odu_pwr:
                    self.move_to(SpruceHackHpState.Unknown)
            case _:
                self.log(f"{self.name} received unexpected message: {message.Header}")
        return Ok(True)

    def process_power(self, watts: int) -> None:
        if watts > self.traits.on_above_w:
            self.move_to(SpruceHackHpState.HpDetectedOn)
        elif watts < self.traits.off_below_w or self.state == SpruceHackHpState.Unknown:
            self.move_to(SpruceHackHpState.HpDetectedOff)

    def move_to(self, state: SpruceHackHpState) -> None:
        if state == self.state:
            return
        self.log(f"{self.state} -> {state}")
        self.state = state
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
