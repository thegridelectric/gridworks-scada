"""The LTN hears the FLO's flo.recommendation on the FLO's topic.

The FLO answers a wrapped request with a wrapped flo.recommendation on
`gw/<flo>/to/ltn/flo-recommendation`, which the broker's MQTT side
delivers to the LTN's scada link. This test stands in for the FLO: the
LTN holds a request for the coming slot, the test publishes the answer
on the FLO's topic, and the LTN bids off it.
"""

import time

import pytest
from gwproto import Message
from paho.mqtt import publish

from actors.ltn.flo_service import flo_alias, flo_recommendation_topic
from gwsproto.names.core.node_names import CoreNodeNames
from tests.actors.test_flo_request import build
from tests.actors.test_ltn_flo_exchange import answer
from tests.utils.scada_live_test_helper import ScadaLiveTest


@pytest.mark.asyncio
async def test_ltn_hears_flo_recommendation_on_the_flos_topic(request: pytest.FixtureRequest) -> None:
    async with ScadaLiveTest(start_all=True, request=request) as h:
        await h.await_for(
            lambda: h.child_to_parent_link.active(),
            "ERROR waiting for the ltn's scada link to activate",
        )
        ltn = h.parent_app.prime_actor
        ltn_alias = ltn.layout.ltn_g_node_alias
        flo = flo_alias(ltn_alias)
        slot_start_s = int(time.time()) // 3600 * 3600 + 3600
        ltn.flo_params = build(g_node_alias=ltn_alias, start_unix_s=slot_start_s)
        recommendation = answer(ltn.flo_params)
        wrapped = Message(Src=flo, Dst=CoreNodeNames.ltn, Payload=recommendation)
        assert wrapped.mqtt_topic() == flo_recommendation_topic(flo)
        mqtt = ltn.settings.scada_mqtt
        tls = None
        port = mqtt.port
        if mqtt.tls.use_tls:
            port = mqtt.tls.port
            tls = {
                "ca_certs": str(mqtt.tls.paths.ca_cert_path),
                "certfile": str(mqtt.tls.paths.cert_path),
                "keyfile": str(mqtt.tls.paths.private_key_path),
            }
        publish.single(
            wrapped.mqtt_topic(),
            wrapped.model_dump_json(by_alias=True),
            hostname=mqtt.host,
            port=port,
            tls=tls,
        )
        await h.await_for(
            lambda: ltn.recommendation is not None
            and ltn.recommendation.CreatedMs == recommendation.CreatedMs,
            "ERROR waiting for the ltn to hold the FLO's flo.recommendation",
        )
        bid = ltn.contract_handler.latest_bid
        assert bid is not None
        assert bid.PqPairs == recommendation.PqPairs
