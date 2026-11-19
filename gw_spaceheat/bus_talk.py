"""One node's conversation with the i2c bus actor.

The bus actor is the single owner of the bus: a board device never touches
it directly. Each operation goes out as a message sent as the device's own
node, and the bus actor's ``i2c.result`` comes back to that node's actor,
which hands it down to the device.
"""

import asyncio
from typing import Any, Optional

from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import ActorClass
from gwsproto.named_types import (
    I2cReadBit,
    I2cReadBytes,
    I2cReadReg,
    I2cResult,
    I2cWriteBit,
    I2cWriteByte,
    I2cWriteReg,
)

from plant import Send

BusOp = I2cWriteBit | I2cReadBit | I2cWriteReg | I2cReadReg | I2cWriteByte | I2cReadBytes


def the_bus_node(layout: HydronicLayout, for_node: str) -> ShNode:
    bus_nodes = [n for n in layout.nodes.values() if n.ActorClass == ActorClass.I2cBus]
    if len(bus_nodes) != 1:
        raise ValueError(
            f"{for_node}: expected exactly one I2cBus node in the "
            f"layout; found {len(bus_nodes)}"
        )
    return bus_nodes[0]


class BusTalk:
    def __init__(self, bus_node: ShNode) -> None:
        self.bus_node = bus_node
        self.timeout_s = 1.0
        self.send: Optional[Send] = None
        self.pending_results: dict[str, "asyncio.Future[I2cResult]"] = {}

    def attach(self, send: Send) -> None:
        self.send = send

    def hears(self, payload: Any) -> bool:
        """Whether the payload was a reply to one of this node's operations.
        A reply that arrives after its operation timed out is dropped: the
        timeout has already been reported."""
        if not isinstance(payload, I2cResult):
            return False
        future = self.pending_results.pop(payload.TriggerId, None)
        if future is not None and not future.done():
            future.set_result(payload)
        return True

    def tell(self, payload: Any) -> None:
        assert self.send is not None
        self.send(self.bus_node, payload)

    async def op(self, payload: BusOp) -> I2cResult | None:
        """Send one operation and await its result, None on timeout."""
        future: "asyncio.Future[I2cResult]" = asyncio.get_running_loop().create_future()
        self.pending_results[payload.TriggerId] = future
        self.tell(payload)
        try:
            return await asyncio.wait_for(future, timeout=self.timeout_s)
        except asyncio.TimeoutError:
            self.pending_results.pop(payload.TriggerId, None)
            return None
