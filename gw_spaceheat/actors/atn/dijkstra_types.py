from __future__ import annotations

from gwsproto.named_types import FloParamsHouse0


class DNode:
    def __init__(
            self,
            parameters: FloParamsHouse0,
            top_temp: float,
            middle_temp: float,
            bottom_temp: float,
            thermocline1: int,
            thermocline2: int,
            time_slice: int | None=0
            ):
        self.params = parameters
        self.time_slice = time_slice
        # State
        self.top_temp = top_temp
        self.middle_temp = middle_temp
        self.bottom_temp = bottom_temp
        self.thermocline1 = thermocline1
        self.thermocline2 = thermocline2
        self.energy = self.get_energy()
        # Dijkstra's algorithm
        self.pathcost = 0 if time_slice==self.params.HorizonHours else 1e9
        self.next_node: DNode | None = None

    def to_string(self):
        return f"{self.top_temp}({self.thermocline1}){self.middle_temp}({self.thermocline2}){self.bottom_temp}"

    def __repr__(self):
        return f"[{self.time_slice}]{self.top_temp}({self.thermocline1}){self.middle_temp}({self.thermocline2}){self.bottom_temp}"

    def get_energy(self) -> float:
        energy_kwh = 0 # TODO: create
        return energy_kwh


class DEdge:
    def __init__(self, tail:DNode, head:DNode, cost:float, hp_heat_out:float):
        self.tail: DNode = tail
        self.head: DNode = head
        self.cost = cost
        self.hp_heat_out = hp_heat_out

    def __repr__(self):
        return f"Edge[{self.tail} --cost:{round(self.cost,3)}, hp:{round(self.hp_heat_out,2)}--> {self.head}]"


def to_kelvin(t):
    return (t-32)*5/9 + 273.15
