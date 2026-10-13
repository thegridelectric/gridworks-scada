from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.relay_control_config import RelayControlConfig


class I2cRelayComponentGt(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.relay.component.gt/000"""

    component_id: UUID4Str
    board_component_id: UUID4Str
    relay_name: PascalCase
    config_list: list[RelayControlConfig]
    display_name: str | None = None
    hw_uid: str | None = None
    type_name: Literal["i2c.relay.component.gt"] = "i2c.relay.component.gt"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "I2cRelayComponentGt":
        """
        Axiom 1: ExactlyOneConfig
        ConfigList SHALL contain exactly one relay.control.config (one relay per component).
        """
        if len(self.config_list) != 1:
            raise ValueError(
                "Axiom 1 failed: ConfigList must contain exactly one relay.control.config."
            )
        return self
