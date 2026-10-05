"""Messages actors send the scada inside one process. None crosses a
process boundary, so none is a sema word."""

from typing import Literal

from gwsproto.property_format import SpaceheatName
from pydantic import BaseModel


class ChannelSubscribe(BaseModel):
    """The sender asks the scada to forward this channel's readings, and
    its flatline, as they arrive. In-process, with no sema word."""

    ChannelName: SpaceheatName
    TypeName: Literal["channel.subscribe"] = "channel.subscribe"
    Version: Literal["000"] = "000"


class MachineStateSubscribe(BaseModel):
    """The sender asks the scada to forward the states of the machine this
    node reports, as they arrive, starting with the latest one the scada
    holds. The node name rather than the machine's handle, since a handle
    moves with the command tree. In-process, with no sema word."""

    NodeName: SpaceheatName
    TypeName: Literal["machine.state.subscribe"] = "machine.state.subscribe"
    Version: Literal["000"] = "000"


class BreakServiceContract(BaseModel):
    """The cold watch's latch has fired with the stores empty: a critical
    zone has been cold for the whole latch and the buffer (and, at an
    AllTanks house, the store) is empty. A scada holding a dispatch
    contract refuses dispatch with ServiceContractBroken and ends the
    contract. In-process, with no sema word."""

    Cause: str
    TypeName: Literal["break.service.contract"] = "break.service.contract"
    Version: Literal["000"] = "000"
