from typing import Any, Optional

from pydantic import ConfigDict

from gwsproto.data_classes.components.component import Component
from gwsproto.enums import ActorClass as ActorClassEnum
from gwsproto.named_types import SpaceheatNodeGt


def parent_hierarchy_name(hierarchy_name: str) -> str:
    last_delimiter = hierarchy_name.rfind(".")
    if last_delimiter == -1:
        return hierarchy_name
    return hierarchy_name[:last_delimiter]


class ShNode(SpaceheatNodeGt):
    """
    A SpaceheatNode, or ShNode, is an organizing principal for the SCADA software.
    ShNodes can represent both underlying physical objects (water tank), measurements of these
    objects (temperature sensing at the top of a water tank), and actors within the code
    (an actor measuring multiple temperatures, or an actor responsible for filtering/smoothing
    temperature data for the purposes of thermostatic control).
    """

    component: Optional[Component[Any, Any]] = None
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __hash__(self) -> int:
        return hash(self.ShNodeId)

    @property
    def sh_node_id(self) -> str:
        return self.ShNodeId

    @property
    def name(self) -> str:
        return self.Name

    @property
    def actor_hierarchy_name(self) -> str:
        if self.ActorHierarchyName is None:
            return self.Name
        return self.ActorHierarchyName

    @property
    def handle(self) -> str:
        if self.Handle is None:
            return self.Name
        return self.Handle

    @property
    def actor_class(self) -> ActorClassEnum:
        return ActorClassEnum(self.ActorClass)

    @property
    def actor_class_str(self) -> str:
        return self.ActorClass

    @property
    def display_name(self) -> Optional[str]:
        return self.DisplayName

    @property
    def component_id(self) -> Optional[str]:
        return self.ComponentId

    @property
    def in_power_metering(self) -> Optional[bool]:
        return self.InPowerMetering

    def __repr__(self) -> str:
        rs = f"ShNode {self.display_name} => {self.name}, "
        if self.has_actor:
            rs += f" ({self.actor_class})"
        else:
            rs += " (passive, no actor)"
        return rs

    @property
    def has_actor(self) -> bool:
        return self.actor_class != ActorClassEnum.NoActor

    def to_gt(self) -> SpaceheatNodeGt:
        # Copy the current instance excluding the extra fields
        return SpaceheatNodeGt(**self.model_dump(exclude={"component"}))
