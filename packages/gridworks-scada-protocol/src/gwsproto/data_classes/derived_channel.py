from pydantic import ConfigDict
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.named_types import DerivedChannelGt

class DerivedChannel(DerivedChannelGt):
    created_by_node: ShNode

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        use_enum_values=True,
    )

    def __hash__(self) -> int:
        return hash(self.Id)

    def to_gt(self) -> DerivedChannelGt:
        return DerivedChannelGt(
            **self.model_dump(exclude={"created_by_node"})
        )