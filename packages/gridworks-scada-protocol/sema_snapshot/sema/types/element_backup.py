from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import SpaceheatName


class ElementBackup(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.element.backup/000"""

    element_relay_names: list[SpaceheatName]
    in_service: bool
    type_name: Literal["gw.element.backup"] = "gw.element.backup"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "ElementBackup":
        """
        Axiom 1: NonEmptyElements
        ElementRelayNames SHALL be non-empty.
        """
        if not self.element_relay_names:
            raise ValueError(
                "Axiom 1 (NonEmptyElements) failed: ElementRelayNames is empty."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "ElementBackup":
        """
        Axiom 2: DistinctElements
        No two entries of ElementRelayNames SHALL be equal.
        """
        seen: set[str] = set()
        for name in self.element_relay_names:
            if name in seen:
                raise ValueError(
                    "Axiom 2 (DistinctElements) failed: ElementRelayNames "
                    f"lists {name} more than once."
                )
            seen.add(name)
        return self
