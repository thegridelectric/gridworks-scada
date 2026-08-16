from typing import Literal
from pydantic import ConfigDict, StrictInt, model_validator
from typing_extensions import Self

from gwsproto.enums import ActorClass
from gwsproto.property_format import HandleName, SpaceheatName, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class SpaceheatNodeGt(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/spaceheat.node.gt/303"""

    Name: SpaceheatName
    ActorHierarchyName: HandleName | None = None
    Handle: HandleName | None = None
    ActorClass: ActorClass
    DisplayName: str | None = None
    ComponentId: UUID4Str | None = None
    BoardComponentId: UUID4Str | None = None
    NameplatePowerW: StrictInt | None = None
    ShNodeId: UUID4Str
    TypeName: Literal["spaceheat.node.gt"] = "spaceheat.node.gt"
    Version: Literal["302"] = "302"

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ActorHierarchy constraints.

        - If ActorClass is "NoActor", ActorHierarchyName MUST be None.
        - If ActorClass is not "NoActor" and ActorHierarchyName is None,
        then ActorClass MUST be "PrimaryScada" or "SecondaryScada".
        - If ActorHierarchyName is present:
            - The final segment SHALL equal Name.
            - All segments SHALL be unique.
        """
        if self.ActorClass == "NoActor":
            if self.ActorHierarchyName is not None:
                raise ValueError(
                    "Axiom 1 failed! "
                    "Nodes with ActorClass 'NoActor' MUST NOT have ActorHierarchyName"
                )

        else:
            if self.ActorHierarchyName is None:
                if self.ActorClass not in [ActorClass.PrimaryScada, ActorClass.SecondaryScada]:
                    raise ValueError(
                        "Axiom 1 failed! "
                        "Only PrimaryScada or SecondaryScada may omit ActorHierarchyName"
                    )
            else:
                segments = self.ActorHierarchyName.split(".")

                if segments[-1] != self.Name:
                    raise ValueError(
                        "Axiom 1 failed! "
                        "Final segment of ActorHierarchyName MUST equal Name"
                    )

                if len(set(segments)) != len(segments):
                    raise ValueError(
                        "Axiom 1 failed! "
                        "ActorHierarchyName segments MUST be unique"
                    )

        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: Handle constraints.

        - If Handle is present:
            - The final segment SHALL equal Name.
            - All segments SHALL be unique.
        """
        if self.Handle is not None:
            segments = self.Handle.split(".")

            if segments[-1] != self.Name:
                raise ValueError(
                    "Axiom 2 failed! "
                    "Final segment of Handle MUST equal Name"
                )

            if len(set(segments)) != len(segments):
                raise ValueError(
                    "Axiom 2 failed! "
                    "Handle segments MUST be unique"
                )

        return self
