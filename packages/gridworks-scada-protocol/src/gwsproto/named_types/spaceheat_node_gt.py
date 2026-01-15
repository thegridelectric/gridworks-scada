from typing import Literal
from pydantic import BaseModel, ConfigDict, StrictInt, model_validator
from typing_extensions import Self

from gwsproto.enums import ActorClass
from gwsproto.property_format import HandleName, SpaceheatName, UUID4Str


class SpaceheatNodeGt(BaseModel):
    Name: SpaceheatName
    ActorHierarchyName: HandleName | None = None
    Handle: HandleName | None = None
    ActorClass: ActorClass
    DisplayName: str | None = None
    ComponentId: str | None = None
    NameplatePowerW: StrictInt | None = None
    InPowerMetering: bool | None = None
    ShNodeId: UUID4Str
    TypeName: Literal["spaceheat.node.gt"] = "spaceheat.node.gt"
    Version: Literal["300"] = "300"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: InPowerMetering requirements.
        If InPowerMetering exists and is true, then NameplatePowerW must exist
        """
        if self.InPowerMetering and self.NameplatePowerW is None:
            raise ValueError(
                "Axiom 1 failed! "
                "If InPowerMetering exists and is true, then NameplatePowerW must exist"
            )
        return self

    model_config = ConfigDict(extra="allow", use_enum_values=True)
