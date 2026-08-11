from typing import Literal

from pydantic import field_validator

from gwsproto.named_types.relay_control_config import RelayControlConfig
from gwsproto.property_format import PascalCase
from gwsproto.type_helpers.component_base import BoardResidentComponentBase


class I2cRelayComponentGt(BoardResidentComponentBase):
    """
    Sema: https://schemas.electricity.works/types/i2c.relay.component.gt/000
    """

    RelayName: PascalCase
    ConfigList: list[RelayControlConfig]

    TypeName: Literal["i2c.relay.component.gt"] = "i2c.relay.component.gt"
    Version: Literal["000"] = "000"

    @field_validator("ConfigList")
    @classmethod
    def check_axiom_1(cls, v: list[RelayControlConfig]) -> list[RelayControlConfig]:
        """Axiom 1: ExactlyOneConfig. ConfigList SHALL contain exactly one
        relay.control.config (one relay per component)."""
        if len(v) != 1:
            raise ValueError(
                "Axiom 1 (ExactlyOneConfig) failed: ConfigList must contain "
                f"exactly one relay.control.config, got {len(v)}."
            )
        return v
