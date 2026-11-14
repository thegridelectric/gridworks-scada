from typing import Literal, Self
from pydantic import StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PositiveInt


class FloTankStorePath(SemaType):
    """Sema: https://schemas.electricity.works/types/flo.tank.store.path/000"""

    store_layers: PositiveInt
    top_f_list: list[StrictInt]
    middle_f_list: list[StrictInt]
    bottom_f_list: list[StrictInt]
    thermocline1_list: list[PositiveInt]
    thermocline2_list: list[PositiveInt]
    empty_store_wh: StrictInt
    full_store_wh: StrictInt
    type_name: Literal["flo.tank.store.path"] = "flo.tank.store.path"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: StepListLengths
        TopFList, MiddleFList, BottomFList, Thermocline1List and
        Thermocline2List SHALL have the same length.
        """
        n = len(self.top_f_list)
        lists = {
            "MiddleFList": self.middle_f_list,
            "BottomFList": self.bottom_f_list,
            "Thermocline1List": self.thermocline1_list,
            "Thermocline2List": self.thermocline2_list,
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
        Axiom 2: ThermoclinesWithinTheStore
        For every step, Thermocline1List[i] SHALL be at most
        Thermocline2List[i], and Thermocline2List[i] SHALL be at most
        StoreLayers.
        """
        for i, (t1, t2) in enumerate(
            zip(self.thermocline1_list, self.thermocline2_list)
        ):
            if t1 > t2 or t2 > self.store_layers:
                raise ValueError(
                    f"Axiom 2 (ThermoclinesWithinTheStore) failed: step {i} has "
                    f"Thermocline1 {t1}, Thermocline2 {t2}, StoreLayers {self.store_layers}; "
                    "Thermocline1 must be at most Thermocline2, at most StoreLayers."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: EmptyBelowFull
        EmptyStoreWh SHALL be less than FullStoreWh.
        """
        if self.empty_store_wh >= self.full_store_wh:
            raise ValueError(
                f"Axiom 3 (EmptyBelowFull) failed: EmptyStoreWh ({self.empty_store_wh}) "
                f"must be less than FullStoreWh ({self.full_store_wh})."
            )
        return self
