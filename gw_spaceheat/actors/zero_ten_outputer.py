"""Implements Dfr Actors"""
import time

from gwproto import Message
from gwsproto.data_classes.house_0_names import H0N
from gwproto.named_types import AnalogDispatch
from result import Ok, Result
from actors.scada_actor import ScadaActor
from scada_app_interface import ScadaAppInterface

class ZeroTenOutputer(ScadaActor):
    def __init__(
        self,
        name: str,
        services: ScadaAppInterface,
    ):
        super().__init__(name, services)
        self.node
        self.dfr_multiplexer = self.layout.node(H0N.zero_ten_out_multiplexer)

    def process_analog_dispatch(self, dispatch: AnalogDispatch) -> None:
        from_node = self.layout.node_by_handle(dispatch.FromHandle)
        if not from_node:
            self.log(f"Ignoring dispatch from  handle {dispatch.FromHandle} - not in layout!!")
            return
        if dispatch.ToHandle != self.node.handle:
            self.log(f"Ignoring dispatch {dispatch} - ToName is not {self.name}!")
            return
        if dispatch.AboutName != self.node.name:
            self.log(f"Ignoring dispatch {dispatch} -- expect AboutName to be about me")
        if dispatch.Value not in range(101):
            self.log(
                f"Igonring dispatch {dispatch} - range out of value. Should be 0-100"
            )
        # self.log(f"Sending {dispatch.Value} to dfr multiplexer")
        self._send_to(
            self.dfr_multiplexer,
            AnalogDispatch(
                FromHandle=self.node.handle,
                ToHandle=self.dfr_multiplexer.handle,
                AboutName=self.name,
                Value=dispatch.Value,
                TriggerId=dispatch.TriggerId,
                UnixTimeMs=int(time.time() * 1000),
            ),
        )

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        self.log(f"Got {message.Payload.TypeName} from {message.Header.Src}")
        payload = message.Payload
        if isinstance(payload, AnalogDispatch):
            try:
                self.process_analog_dispatch(payload)
            except Exception as e:
                self.log(f"Trouble with process_analog_dispatch: {e}")
        return Ok(True)

    def start(self) -> None:
        ...

    def stop(self) -> None:
        """
        IOLoop will take care of shutting down webserver interaction.
        Here we stop periodic reporting task.
        """
        ...

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""
        ...
