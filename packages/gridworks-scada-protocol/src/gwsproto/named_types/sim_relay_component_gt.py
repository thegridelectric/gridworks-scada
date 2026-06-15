from collections.abc import Sequence
from typing import Literal

from pydantic import ConfigDict

from gwsproto.named_types.component_gt import ComponentGt
from gwsproto.named_types.relay_actor_config import RelayActorConfig


class SimRelayComponentGt(ComponentGt):
    """
    A simulated relay component — what the scada-side SimRelayActor's relay node uses
    in a simulated layout.

    Sema word: ``sim.relay.component.gt``. Structurally a relay component (ComponentId,
    DeviceType, a ConfigList of relay.actor.config), but a distinct ``sim.*`` type so a
    simulated layout is visibly simulated by construction. Parallel to
    SimSensorComponentGt.
    """

    ConfigList: Sequence[RelayActorConfig]
    TypeName: Literal["sim.relay.component.gt"] = "sim.relay.component.gt"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(extra="allow")
