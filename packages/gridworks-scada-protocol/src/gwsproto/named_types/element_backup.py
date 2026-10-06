from typing import List, Literal

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class ElementBackup(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.element.backup/000"""

    ElementRelayNames: List[SpaceheatName]
    InService: bool
    TypeName: Literal["gw.element.backup"] = "gw.element.backup"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: NonEmptyElements. ElementRelayNames SHALL be non-empty.
        """
        if not self.ElementRelayNames:
            raise ValueError(
                "Axiom 1 (NonEmptyElements) failed: ElementRelayNames is empty."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: DistinctElements. No two entries of ElementRelayNames SHALL
        be equal.
        """
        if len(set(self.ElementRelayNames)) != len(self.ElementRelayNames):
            raise ValueError(
                "Axiom 2 (DistinctElements) failed: ElementRelayNames lists a "
                "relay more than once."
            )
        return self
