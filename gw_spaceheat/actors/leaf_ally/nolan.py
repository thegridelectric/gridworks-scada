"""NolanLeafAlly — the Nolan family's LeafAlly: it speaks the transactive
handshake but actuates nothing.

A Nolan home carries an `la` node like a House0 home does, so the LeafAlly
loader must be able to select an implementation for it. Nolan has no thermal
store to charge or discharge against a dispatch contract, so this
implementation runs no control loop and commands no actuator.

It does take part in the handshake, because the scada's contract flow expects
it: on receiving a SlowDispatchContract the scada hands the ally the command
tree and waits for `SuitUp` before treating the ally as in control. An ally
that stayed silent would leave the scada mid-handshake, so this one suits up,
holds, and goes dormant when told. Accepting the contract and doing nothing
with it is the honest Nolan behaviour for now; replace it when Nolan gains a
real transactive path.
"""

import time
from typing import Optional, Sequence

from gwproactor import MonitoredName
from gwproto import Message
from result import Ok, Result

from actors.sh_node_actor import ShNodeActor
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import LeafAllyBufferOnlyState
from gwsproto.named_types import GoDormant, SingleMachineState, SlowDispatchContract, SuitUp
from scada_app_interface import ScadaAppInterface


class NolanLeafAlly(ShNodeActor):
    def __init__(self, name: str, services: ScadaAppInterface) -> None:
        super().__init__(name, services)
        # Nolan has no ally state machine of its own; it reports the shared
        # Dormant/Initializing values so snapshot and report consumers see a
        # well-formed state.
        self.state: LeafAllyBufferOnlyState = LeafAllyBufferOnlyState.Dormant
        self.prev_state: Optional[LeafAllyBufferOnlyState] = None
        self._stop_requested = False

    def start(self) -> None:
        """No loop to run; announce the initial state so the first snapshot
        carries an ally row."""
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=LeafAllyBufferOnlyState.enum_name(),
                State=self.state,
                UnixMs=int(time.time() * 1000),
            ),
        )

    def stop(self) -> None:
        self._stop_requested = True

    async def join(self) -> None:
        ...

    def wake_up(self) -> None:
        """Tell the scada the ally is in control, then do nothing with it."""
        self.prev_state = self.state
        self.state = LeafAllyBufferOnlyState.Initializing
        self._send_to(
            self.primary_scada, SuitUp(ToNode=H0N.primary_scada, FromNode=self.name)
        )

    def go_dormant(self) -> None:
        self.prev_state = self.state
        self.state = LeafAllyBufferOnlyState.Dormant

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        match message.Payload:
            case SlowDispatchContract():  # the scada's WakeUp for the ally
                if self.state == LeafAllyBufferOnlyState.Dormant:
                    self.wake_up()
            case GoDormant():
                if self.state != LeafAllyBufferOnlyState.Dormant:
                    self.go_dormant()
        return Ok(True)

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        """Nothing to watchdog: no loop to go quiet."""
        return []
