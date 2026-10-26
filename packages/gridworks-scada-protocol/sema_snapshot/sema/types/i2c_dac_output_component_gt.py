from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.dac_output_config import DacOutputConfig


class I2cDacOutputComponentGt(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.dac.output.component.gt/000"""

    component_id: UUID4Str
    board_component_id: UUID4Str
    dac_name: PascalCase
    config_list: list[DacOutputConfig]
    display_name: str | None = None
    hw_uid: str | None = None
    type_name: Literal["i2c.dac.output.component.gt"] = "i2c.dac.output.component.gt"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "I2cDacOutputComponentGt":
        """
        Axiom 1: ExactlyOneConfig
        ConfigList SHALL contain exactly one dac.output.config (one output channel per component).
        """
        if len(self.config_list) != 1:
            raise ValueError(
                "Axiom 1 (ExactlyOneConfig) failed: ConfigList must contain exactly "
                f"one dac.output.config, got {len(self.config_list)}."
            )
        return self
