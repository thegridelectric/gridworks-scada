"""The FLO service the LTN asks and the topics the exchange goes on.

The universe's one FLO is the GNode `<universe>.flo` under the universe
root, so the LTN finds it from its own alias. The request is a gw-wrapped
`flo.params` on the scada broker addressed to the flo class
(`gw/<ltn>/to/flo/flo-params`), which the broker bridges onto `amq.topic`
where the service's queue is bound. The answer comes back the same way,
a gw-wrapped `flo.recommendation` on the service's own topic to the ltn
class (`gw/<flo>/to/ltn/flo-recommendation`).
"""

from gwproto.topic import MQTTTopic
from gwsproto.named_types import FloRecommendation
from gwsproto.names.core.node_names import CoreNodeNames

from universe import universe_of_alias

# The FLO's name under the universe root.
FLO_ROOT_NAME = "flo"

# The gwbase RoutingClass.Flo token: the destination segment of a wrapped
# request, so the wire key `gw.<src>.to.flo.<type>` resolves to the FLO class
# on the rabbit side.
FLO_DST = "flo"

GW_ENVELOPE = "gw"


def flo_alias(ltn_g_node_alias: str) -> str:
    """The FLO of the LTN's universe: `<universe>.flo`."""
    return f"{universe_of_alias(ltn_g_node_alias)}.{FLO_ROOT_NAME}"


def flo_recommendation_topic(flo_g_node_alias: str) -> str:
    """The MQTT topic the FLO's wrapped `flo.recommendation` arrives on."""
    return MQTTTopic.encode(
        envelope_type=GW_ENVELOPE,
        src=flo_g_node_alias,
        dst=CoreNodeNames.ltn,
        message_type=FloRecommendation.model_fields["TypeName"].default,
    )
