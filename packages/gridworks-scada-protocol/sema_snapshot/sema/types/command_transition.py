from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import NonEmptyString


class CommandTransition(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.command.transition/000"""

    event: NonEmptyString
    to_state: NonEmptyString
    type_name: Literal["gw.command.transition"] = "gw.command.transition"
    version: Literal["000"] = "000"
