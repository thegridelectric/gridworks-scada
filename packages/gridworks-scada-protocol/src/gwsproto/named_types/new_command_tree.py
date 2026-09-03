from typing import List, Literal

from pydantic import model_validator

from gwsproto.named_types.spaceheat_node_gt import SpaceheatNodeGt
from gwsproto.property_format import LeftRightDotStr, UTCMilliseconds
from gwsproto.type_helpers.command_tree_axioms import (
    check_actuator_leaves,
    check_prefix_closed_handles,
)
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
        check_prefix_closed_handles(self.ShNodes, "Axiom 1 (PrefixClosedHandles)")
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "NewCommandTree":
        """
        Axiom 2: ActuatorLeaves.
        a. Every actuator (Relay, ZeroTenOutputer, HpTwin) SHALL have a dotted
        effective handle and SHALL be a leaf. b. Every leaf SHALL be an actuator
        or a command node (LocalControl, LeafAlly, PicoCycler, HpBoss, SiegLoop,
        or a NoActor whose handle parent is the LocalControl node).
        """
        check_actuator_leaves(self.ShNodes, "Axiom 2 (ActuatorLeaves)")
        return self
