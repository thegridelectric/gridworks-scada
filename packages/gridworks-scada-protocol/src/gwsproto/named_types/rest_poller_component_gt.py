from typing import Literal

from gwsproto.named_types import ComponentGt
from gwsproto.named_types.rest_poller_gt import RESTPollerSettings


class RESTPollerComponentGt(ComponentGt):
    Rest: RESTPollerSettings
    TypeName: Literal["rest.poller.component.gt"] = "rest.poller.component.gt"
