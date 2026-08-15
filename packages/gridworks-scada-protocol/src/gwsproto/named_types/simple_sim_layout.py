
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from typing import Literal



class SimpleSimLayout(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/gw1.simple.sim.layout/000

    Minimal baseline stub (TypeName + Version only) for the simple simulated-test
    -environment hydronic layout (1 storage tank, 360-gallon store). Sema is the
    source of truth; built up bit by bit, then hand-ported here and tested via the
    layout round-trip script.
    """

    TypeName: Literal["gw1.simple.sim.layout"] = "gw1.simple.sim.layout"
    Version: Literal["000"] = "000"
