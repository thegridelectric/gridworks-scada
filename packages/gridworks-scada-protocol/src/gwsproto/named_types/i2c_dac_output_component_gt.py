from typing import Literal

from pydantic import field_validator

from gwsproto.named_types.dac_output_config import DacOutputConfig
from gwsproto.property_format import PascalCase
from gwsproto.type_helpers.component_base import BoardResidentComponentBase


class I2cDacOutputComponentGt(BoardResidentComponentBase):
    """
    Sema: https://schemas.electricity.works/types/i2c.dac.output.component.gt/000
    """

    DacName: PascalCase
    ConfigList: list[DacOutputConfig]

    TypeName: Literal["i2c.dac.output.component.gt"] = "i2c.dac.output.component.gt"
    Version: Literal["000"] = "000"

    @field_validator("ConfigList")
    @classmethod
    def check_axiom_1(cls, v: list[DacOutputConfig]) -> list[DacOutputConfig]:
        """Axiom 1: ExactlyOneConfig. ConfigList SHALL contain exactly one
        dac.output.config (one output channel per component)."""
        if len(v) != 1:
            raise ValueError(
                "Axiom 1 (ExactlyOneConfig) failed: ConfigList must contain "
                f"exactly one dac.output.config, got {len(v)}."
            )
        return v
