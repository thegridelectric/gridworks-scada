from typing import Literal

from pydantic import (
    ConfigDict,
    PositiveInt,
    StrictInt,
    field_validator,
    model_validator,
)
from typing_extensions import Self

from gwsproto.enums import TelemetryName
from gwsproto.named_types.component_attribute_class_gt import ComponentAttributeClassGt
from gwsproto.property_format import (
    check_is_ads1115_i2c_address,
)


class Ads111xBasedCacGt(ComponentAttributeClassGt):
    AdsI2cAddressList: list[StrictInt]
    TotalTerminalBlocks: PositiveInt
    TelemetryNameList: list[TelemetryName]
    TypeName: Literal["ads111x.based.cac.gt"] = "ads111x.based.cac.gt"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    @field_validator("AdsI2cAddressList")
    @classmethod
    def _check_ads_i2c_address_list(cls, v: list[int]) -> list[int]:
        try:
            for elt in v:
                check_is_ads1115_i2c_address(elt)
        except ValueError as e:
            raise ValueError(
                f"AdsI2cAddressList element failed Ads1115I2cAddress format validation: {e}",
            ) from e
        return v

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: TerminalBlock Ads Chip consistency.
        TotalTerminalBlocks should be greater than 4 * (len(AdsI2cAddressList) - 1 ) and less than or equal to 4*len(AdsI2cAddressList)
        """
        # Implement check for axiom 1"
        return self
