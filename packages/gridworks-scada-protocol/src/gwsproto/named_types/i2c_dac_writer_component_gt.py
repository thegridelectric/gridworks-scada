from collections.abc import Sequence
from typing import Literal, Self

from pydantic import model_validator

from gwsproto.named_types.i2c_dac_channel_config import I2cDacChannelConfig
from gwsproto.property_format import PascalCase
from gwsproto.type_helpers.component_base import BoardResidentComponentBase


class I2cDacWriterComponentGt(BoardResidentComponentBase):
    """
    Sema: https://schemas.electricity.works/types/i2c.dac.writer.component.gt/000
    """

    DacName: PascalCase
    ConfigList: Sequence[I2cDacChannelConfig]

    TypeName: Literal["i2c.dac.writer.component.gt"] = "i2c.dac.writer.component.gt"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: DacChannelUniqueness
        DacChannel values SHALL be unique across the ConfigList.
        """
        channels = [c.DacChannel for c in self.ConfigList]
        dupes = sorted({str(c) for c in channels if channels.count(c) > 1})
        if dupes:
            raise ValueError(
                "Axiom 1 (DacChannelUniqueness) failed: duplicate DacChannel "
                f"value(s) {dupes} in ConfigList."
            )
        return self
