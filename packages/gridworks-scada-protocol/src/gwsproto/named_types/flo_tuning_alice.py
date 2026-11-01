from typing import Literal

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class FloTuningAlice(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/flo.tuning.alice/000"""

    TypeName: Literal["flo.tuning.alice"] = "flo.tuning.alice"
    Version: Literal["000"] = "000"
