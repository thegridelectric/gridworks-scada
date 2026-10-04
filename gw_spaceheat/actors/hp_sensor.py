"""hp-sensor: the heat pump as the scada senses it."""

from gwproto.message import Message
from result import Ok, Result

from actors.sh_node_actor import ShNodeActor


class HpSensor(ShNodeActor):
    """The actor at the hp-sensor node, where the heat pump's sensed running
    state is reported as a machine state. Its threshold machine is not built:
    it subscribes to nothing and reports nothing."""

    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...

    async def join(self) -> None:
        ...

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        self.log(f"{self.name} received unexpected message: {message.Header}")
        return Ok(True)
