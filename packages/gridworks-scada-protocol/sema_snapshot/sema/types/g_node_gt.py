from typing import Literal, Self
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import BaseGNodeClass
from sema_snapshot.sema.enums import GNodeStatus
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UUID4Str


class GNodeGt(SemaType):
    """Sema: https://schemas.electricity.works/types/g.node.gt/006"""

    g_node_id: UUID4Str
    alias: LeftRightDot
    base_class: BaseGNodeClass
    g_node_class: str
    status: GNodeStatus
    prev_alias: LeftRightDot | None = None
    position_point_id: UUID4Str | None = None
    display_name: str | None = None
    type_name: Literal["g.node.gt"] = "g.node.gt"
    version: Literal["006"] = "006"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ClassConsistency
        a. If BaseClass is not Logical, GNodeClass SHALL equal the string value of BaseClass.
        b. If BaseClass is Logical, GNodeClass SHALL NOT equal any value of base.g.node.class other than Logical.
        """
        if self.base_class != BaseGNodeClass.Logical:
            if self.g_node_class != self.base_class.value:
                raise ValueError(
                    f"Axiom 1 (ClassConsistency, clause a) failed: Physical GNodes must align BaseClass and GNodeClass. "
                    f"Expected GNodeClass='{self.base_class.value}' "
                    f"but got '{self.g_node_class}'."
                )
        elif (
            self.g_node_class in BaseGNodeClass.values()
            and self.g_node_class != BaseGNodeClass.Logical.value
        ):
            raise ValueError(
                "Axiom 1 (ClassConsistency, clause b) failed: Logical GNodes must not use a non-Logical "
                "base.g.node.class value as GNodeClass."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: PhysicalGNodeLocations
        If Status is Active and BaseClass != Logical, PositionPointId SHALL NOT be null.
        """
        if (
            self.status == GNodeStatus.Active
            and self.base_class != BaseGNodeClass.Logical
            and self.position_point_id is None
        ):
            raise ValueError(
                "Axiom 2 failed: An Active physical GNode must have a "
                f"PositionPointId. BaseClass='{self.base_class.value}' is "
                "Active with no location."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: AliasTransitionConsistency
        If PrevAlias is not null, it SHALL differ from Alias.
        """
        if self.prev_alias is not None and self.prev_alias == self.alias:
            raise ValueError(
                "Axiom 3 failed: PrevAlias must differ from Alias when present."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: GNodeClassNamespacing
        GNodeClass SHALL be a non-empty string containing no whitespace
        """
        if not self.g_node_class:
            raise ValueError("Axiom 4 failed: GNodeClass must be non-empty.")
        if any(char.isspace() for char in self.g_node_class):
            raise ValueError("Axiom 4 failed: GNodeClass must not contain whitespace.")
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> Self:
        """
        Axiom 5: AliasSuffixSemantics
        a. Alias SHALL end with ".ta" if and only if GNodeClass is "TerminalAsset".
        b. Alias SHALL end with ".scada" if and only if GNodeClass is "Scada".
        """
        alias_has_ta_suffix = self.alias.endswith(".ta")
        if (self.g_node_class == "TerminalAsset") != alias_has_ta_suffix:
            raise ValueError(
                'Axiom 5 (AliasSuffixSemantics, clause a) failed: Alias must end with ".ta" if and only if '
                'GNodeClass is "TerminalAsset".'
            )

        alias_has_scada_suffix = self.alias.endswith(".scada")
        if (self.g_node_class == "Scada") != alias_has_scada_suffix:
            raise ValueError(
                'Axiom 5 (AliasSuffixSemantics, clause b) failed: Alias must end with ".scada" if and only if '
                'GNodeClass is "Scada".'
            )
        return self

    @model_validator(mode="after")
    def check_axiom_6(self) -> Self:
        """
        Axiom 6: GNodeAliasHasBody
        a. Alias SHALL have at least two dotted words (the universe segment is a namespace, not a GNodeAlias, so the shortest valid GNodeAlias is like "d1.isone").
        b. If PrevAlias is present, it SHALL likewise have at least two dotted words.
        """
        if len(self.alias.split(".")) < 2:
            raise ValueError(
                "Axiom 6 (GNodeAliasHasBody, clause a) failed: Alias must have at least two dotted words "
                "(the universe segment alone is a namespace, not a GNodeAlias)."
            )
        if self.prev_alias is not None and len(self.prev_alias.split(".")) < 2:
            raise ValueError(
                "Axiom 6 (GNodeAliasHasBody, clause b) failed: PrevAlias must have at least two dotted words "
                "(the universe segment alone is a namespace, not a GNodeAlias)."
            )
        return self
