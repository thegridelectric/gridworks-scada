from typing import Literal

from gwsproto import property_format
from gwsproto.property_format import LeftRightDotStr, UTCMilliseconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class ScadaCommit(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.scada.commit/000"""

    ScadaAlias: LeftRightDotStr
    # The field shadows the format name inside the class body, so the
    # annotation goes through the module.
    GitCommit: property_format.GitCommit
    MessageCreatedMs: UTCMilliseconds
    TypeName: Literal["gw.scada.commit"] = "gw.scada.commit"
    Version: Literal["000"] = "000"
