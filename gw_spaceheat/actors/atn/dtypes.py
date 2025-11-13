from __future__ import annotations

from gwsproto.named_types import FloParamsHouse0


class DNode:
    def __init__(self, parameters: FloParamsHouse0, time_slice: int | None=0):
        self.params = parameters
        self.time_slice = time_slice
        self.energy = self.get_energy()
        self.pathcost = 0 if time_slice==self.params.HorizonHours else 1e9
        self.next_node: DNode | None = None

    def get_energy(self) -> float:
        energy_kwh = 0 # TODO: create
        return energy_kwh


class DEdge:
    def __init__(self, tail:DNode, head:DNode, cost:float):
        self.tail: DNode = tail
        self.head: DNode = head
        self.cost = cost

    def __repr__(self):
        return f"Edge[{self.tail} --cost:{round(self.cost,3)}--> {self.head}]"