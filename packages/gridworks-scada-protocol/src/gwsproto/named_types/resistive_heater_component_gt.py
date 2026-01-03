from typing import Literal, Optional

from gwsproto.named_types import ComponentGt


class ResistiveHeaterComponentGt(ComponentGt):
    TestedMaxHotMilliOhms: Optional[int] = None
    TestedMaxColdMilliOhms: Optional[int] = None
    TypeName: Literal["resistive.heater.component.gt"] = "resistive.heater.component.gt"
