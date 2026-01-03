from pydantic import ConfigDict

from gwsproto.data_classes.sh_node import ShNode
from gwsproto.named_types import SynthChannelGt


class SynthChannel(SynthChannelGt):
    created_by_node: ShNode

    model_config = ConfigDict(arbitrary_types_allowed=True, use_enum_values=True)

    def __hash__(self) -> int:
        return hash(self.Id)

    def to_gt(self) -> SynthChannelGt:
        # Copy the current instance excluding the extra fields
        return SynthChannelGt(**self.model_dump(exclude={"created_by_node"}))
