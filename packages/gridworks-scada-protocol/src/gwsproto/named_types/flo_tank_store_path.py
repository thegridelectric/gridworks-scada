from typing import List, Literal

from pydantic import PositiveInt, StrictInt, model_validator
from typing_extensions import Self

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class FloTankStorePath(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/flo.tank.store.path/000"""

    StoreLayers: PositiveInt
    TopFList: List[StrictInt]
    MiddleFList: List[StrictInt]
    BottomFList: List[StrictInt]
    Thermocline1List: List[PositiveInt]
    Thermocline2List: List[PositiveInt]
    EmptyStoreWh: StrictInt
    FullStoreWh: StrictInt
    TypeName: Literal["flo.tank.store.path"] = "flo.tank.store.path"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: StepListLengths.
        TopFList, MiddleFList, BottomFList, Thermocline1List and
        Thermocline2List SHALL have the same length.
        """
        n = len(self.TopFList)
        lists = {
            "MiddleFList": self.MiddleFList,
            "BottomFList": self.BottomFList,
            "Thermocline1List": self.Thermocline1List,
            "Thermocline2List": self.Thermocline2List,
        }
        for name, values in lists.items():
            if len(values) != n:
                raise ValueError(
                    f"Axiom 1 (StepListLengths) failed: {name} ({len(values)}) must "
                    f"have the length of TopFList ({n})."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: ThermoclinesWithinTheStore.
        For every step, Thermocline1List[i] SHALL be at most
        Thermocline2List[i], and Thermocline2List[i] SHALL be at most
        StoreLayers.
        """
        for i, (t1, t2) in enumerate(zip(self.Thermocline1List, self.Thermocline2List)):
            if t1 > t2 or t2 > self.StoreLayers:
                raise ValueError(
                    f"Axiom 2 (ThermoclinesWithinTheStore) failed: step {i} has "
                    f"Thermocline1 {t1}, Thermocline2 {t2}, StoreLayers {self.StoreLayers}; "
                    "Thermocline1 must be at most Thermocline2, at most StoreLayers."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: EmptyBelowFull.
        EmptyStoreWh SHALL be less than FullStoreWh.
        """
        if self.EmptyStoreWh >= self.FullStoreWh:
            raise ValueError(
                f"Axiom 3 (EmptyBelowFull) failed: EmptyStoreWh ({self.EmptyStoreWh}) "
                f"must be less than FullStoreWh ({self.FullStoreWh})."
            )
        return self
