from typing import Literal

from pydantic import PositiveInt, StrictInt, model_validator
from typing_extensions import Self

from gwsproto.property_format import LeftRightDotStr, UTCSeconds, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class SlowDispatchContract(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/slow.dispatch.contract/001"""

    ScadaAlias: LeftRightDotStr
    StartS: UTCSeconds
    DurationMinutes: PositiveInt
    AvgPowerWatts: StrictInt
    ContractId: UUID4Str
    DispatchTerms: LeftRightDotStr
    TypeName: Literal["slow.dispatch.contract"] = "slow.dispatch.contract"
    Version: Literal["001"] = "001"

    def contract_end_s(self) -> int:
        return self.StartS + self.DurationMinutes * 60

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: StartOnFiveMinutes.
        StartS SHALL be a multiple of 300.
        """
        if self.StartS % 300 != 0:
            raise ValueError(
                "Axiom 1 (StartOnFiveMinutes) failed: StartS must be a multiple "
                f"of 300; got {self.StartS % 300} seconds past"
            )
        return self
