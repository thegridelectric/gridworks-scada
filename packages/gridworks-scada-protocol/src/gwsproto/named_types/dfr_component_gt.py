from collections.abc import Sequence
from typing import Literal

from pydantic import PositiveInt

from gwsproto.named_types import ComponentGt
from gwsproto.named_types.dfr_config import DfrConfig


class DfrComponentGt(ComponentGt):
    ConfigList: Sequence[DfrConfig]
    I2cAddressList: list[PositiveInt]
    TypeName: Literal["dfr.component.gt"] = "dfr.component.gt"
    Version: Literal["000"] = "000"
