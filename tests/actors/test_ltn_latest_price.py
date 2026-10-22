"""The LTN hears the MarketMaker's latest.price on the rjb bridge topic.

The maker broadcasts the bare latest.price word on its mic exchange; the
broker's rjb bridge tap carries it to the MQTT side, where the LTN's
scada link is subscribed to the maker's topic. This test stands in for the
maker: it publishes the word on that topic and waits for the LTN's
contract handler to hold it.
"""

import time
import uuid

import pytest
from paho.mqtt import publish

from actors.ltn import Ltn
from gwsproto.enums import MarketPriceUnit, MarketTypeName
from gwsproto.named_types import LatestPrice
from tests.utils.scada_live_test_helper import ScadaLiveTest


@pytest.mark.asyncio
async def test_ltn_hears_latest_price_on_rjb(request: pytest.FixtureRequest) -> None:
    async with ScadaLiveTest(start_all=True, request=request) as h:
        await h.await_for(
            lambda: h.child_to_parent_link.active(),
            "ERROR waiting for the ltn's scada link to activate",
        )
        ltn = h.parent_app.prime_actor
        alias = ltn.settings.market_maker_alias
        slot_start_s = int(time.time()) // 3600 * 3600
        price = LatestPrice(
            FromGNodeAlias=alias,
            PriceTimes1000=123456,
            PriceUnit=MarketPriceUnit.USDPerMWh,
            MarketSlotName=f"e.{MarketTypeName.rt60gate5.value}.{alias}.{slot_start_s}",
            MessageId=str(uuid.uuid4()),
        )
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
            Ltn.latest_price_topic(alias),
            price.model_dump_json(by_alias=True),
            hostname=mqtt.host,
            port=port,
            tls=tls,
        )
        await h.await_for(
            lambda: ltn.contract_handler.latest_price is not None
            and ltn.contract_handler.latest_price.MessageId == price.MessageId,
            "ERROR waiting for the ltn to hold the maker's latest.price",
        )
