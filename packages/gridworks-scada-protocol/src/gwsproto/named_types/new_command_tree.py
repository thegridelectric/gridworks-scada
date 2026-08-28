from typing import List, Literal

from pydantic import model_validator

from gwsproto.named_types.spaceheat_node_gt import SpaceheatNodeGt
from gwsproto.property_format import LeftRightDotStr, UTCMilliseconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class NewCommandTree(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/new.command.tree/002"""

    FromGNodeAlias: LeftRightDotStr
    ShNodes: List[SpaceheatNodeGt]
    UnixMs: UTCMilliseconds
    TypeName: Literal["new.command.tree"] = "new.command.tree"
    Version: Literal["002"] = "002"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "NewCommandTree":
        """
        Axiom 1: PrefixClosedHandles.
        Let the effective handle of an ShNode be its Handle if present, otherwise
        its Name. The set of effective handles SHALL be prefix-closed: for every
        ShNode in ShNodes, each dot-separated prefix of its effective handle SHALL
        also be the effective handle of some ShNode in ShNodes.
        """
        effective = {
            node.Handle if node.Handle is not None else node.Name
            for node in self.ShNodes
        }
        for handle in sorted(effective):
            segments = handle.split(".")
            for n in range(1, len(segments)):
                prefix = ".".join(segments[:n])
                if prefix not in effective:
                    raise ValueError(
                        f"Axiom 1 (PrefixClosedHandles) failed: effective handle "
                        f"{handle!r} has prefix {prefix!r} that is not the "
                        "effective handle of any ShNode"
                    )
        return self
