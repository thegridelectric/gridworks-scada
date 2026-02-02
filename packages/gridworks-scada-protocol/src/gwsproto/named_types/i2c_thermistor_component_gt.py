from typing import Literal

from pydantic import ConfigDict, StrictInt, model_validator
from typing_extensions import Self

from gwsproto.property_format import SpaceheatName
from gwsproto.named_types.component_gt import ComponentGt



class I2cThermistorComponentGt(ComponentGt):
    I2cBus: SpaceheatName
    I2cAddressList: list[StrictInt]
    TypeName: Literal["i2c.thermistor.component.gt"] = (
        "i2c.thermistor.component.gt"
    )
    Version: Literal["001"] = "001"

    model_config = ConfigDict(extra="allow", use_enum_values=True)


