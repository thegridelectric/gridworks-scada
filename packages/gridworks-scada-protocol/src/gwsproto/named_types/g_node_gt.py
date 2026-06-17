from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator
from typing_extensions import Self

from gwsproto.enums import BaseGNodeClass, GNodeStatus
from gwsproto.property_format import LeftRightDotStr, UUID4Str


class GNodeGt(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/g.node.gt/004
    """

    GNodeId: UUID4Str
    Alias: LeftRightDotStr
    BaseClass: BaseGNodeClass
    GNodeClass: str
    Status: GNodeStatus
    PrevAlias: Optional[LeftRightDotStr] = None
    PositionPointId: Optional[UUID4Str] = None
    DisplayName: Optional[str] = None
    TypeName: Literal["g.node.gt"] = "g.node.gt"
    Version: Literal["004"] = "004"

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ClassConsistency
        a. If BaseClass is not Logical, GNodeClass SHALL equal the string value of BaseClass.
        b. If BaseClass is Logical, GNodeClass SHALL NOT equal any value of base.g.node.class
           other than Logical.
        """
        if self.BaseClass != BaseGNodeClass.Logical:
            if self.GNodeClass != self.BaseClass.value:
                raise ValueError(
                    "Axiom 1 failed: Physical GNodes must align BaseClass and GNodeClass. "
                    f"Expected GNodeClass='{self.BaseClass.value}' but got '{self.GNodeClass}'."
                )
        elif (
            self.GNodeClass in BaseGNodeClass.values()
            and self.GNodeClass != BaseGNodeClass.Logical.value
        ):
            raise ValueError(
                "Axiom 1 failed: Logical GNodes must not use a non-Logical "
                "base.g.node.class value as GNodeClass."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: PhysicalGNodeLocations
        If BaseClass != Logical, PositionPointId SHALL NOT be null.
        """
        if self.BaseClass != BaseGNodeClass.Logical and self.PositionPointId is None:
            raise ValueError(
                "Axiom 2 failed: Physical GNodes must have a PositionPointId. "
                f"BaseClass='{self.BaseClass.value}' has no location."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: AliasTransitionConsistency
        If PrevAlias is not null, it SHALL differ from Alias.
        """
        if self.PrevAlias is not None and self.PrevAlias == self.Alias:
            raise ValueError(
                "Axiom 3 failed: PrevAlias must differ from Alias when present."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: GNodeClassNamespacing
        GNodeClass SHALL be a non-empty string containing no whitespace.
        """
        if not self.GNodeClass:
            raise ValueError("Axiom 4 failed: GNodeClass must be non-empty.")
        if any(char.isspace() for char in self.GNodeClass):
            raise ValueError("Axiom 4 failed: GNodeClass must not contain whitespace.")
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> Self:
        """
        Axiom 5: AliasSuffixSemantics
        a. Alias SHALL end with ".ta" iff GNodeClass is "TerminalAsset".
        b. Alias SHALL end with ".scada" iff GNodeClass is "Scada".
        """
        if (self.GNodeClass == "TerminalAsset") != self.Alias.endswith(".ta"):
            raise ValueError(
                'Axiom 5 failed: Alias must end with ".ta" iff GNodeClass is "TerminalAsset".'
            )
        if (self.GNodeClass == "Scada") != self.Alias.endswith(".scada"):
            raise ValueError(
                'Axiom 5 failed: Alias must end with ".scada" iff GNodeClass is "Scada".'
            )
        return self
