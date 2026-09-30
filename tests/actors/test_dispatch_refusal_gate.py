"""The dispatch refusal gate: while the ops word says AcceptsDispatch is
false, whatever the reason, a contract offer gets AllyGivesUp from the
LeafAlly wrapper on both families, the scada falls back to LocalControl,
and the LTN, reading the operating status, does not dispatch. With
AcceptsDispatch true the family's ally takes the offer."""

import json
import time
import uuid
from pathlib import Path

import pytest
from gwproto import Message

from actors.leaf_ally_loader import LeafAlly
from gwsproto.enums import DispatchRefusalReason, MainAutoState, SlowDispatchContractStatus
from gwsproto.named_types import AllyGivesUp, SlowContractHeartbeat, SlowDispatchContract
from gwsproto.names.core.node_names import CoreNodeNames
from sema_to_dc import load_layout
from tests.utils.scada_live_test_helper import ScadaLiveTest

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
    "house0-orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
}


def refusing_ops(tmp_path: Path, ops_file: str, reason: DispatchRefusalReason) -> Path:
    ops = json.loads((CONFIG / ops_file).read_text())
    ops["AcceptsDispatch"] = False
    ops["DispatchRefusalReason"] = reason.value
    if reason is DispatchRefusalReason.Standby:
        ops["Standby"] = True
    path = tmp_path / ops_file
    path.write_text(json.dumps(ops))
    return path


def offer(ltn) -> SlowContractHeartbeat:
    start_s = (int(time.time()) // 300) * 300 + 300
    return SlowContractHeartbeat(
        FromNode=ltn.node.name,
        Contract=SlowDispatchContract(
            ScadaAlias=ltn.layout.scada_g_node_alias,
            StartS=start_s,
            DurationMinutes=60,
            AvgPowerWatts=1000,
            OilBoilerOn=False,
            ContractId=str(uuid.uuid4()),
        ),
        Status=SlowDispatchContractStatus.Created,
        WattHoursUsed=0,
        MessageCreatedMs=int(time.time() * 1000),
        MyDigit=5,
        YourLastDigit=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", list(DispatchRefusalReason))
@pytest.mark.parametrize("pair", sorted(PAIRS))
async def test_refusing_scada_gives_up_on_every_offer(
    request: pytest.FixtureRequest, tmp_path: Path, pair: str, reason: DispatchRefusalReason
) -> None:
    layout_file, ops_file = PAIRS[pair]
    ops_path = refusing_ops(tmp_path, ops_file, reason)
    layout = load_layout(CONFIG / layout_file, ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as tst:
        tst.start_child1()
        tst.start_parent()
        await tst.await_for(
            lambda: tst.child_to_parent_link.active(),
            "ERROR waiting for scada to ltn link",
        )
        scada = tst.child1_app.scada
        ltn = tst.parent_app.ltn
        await tst.await_for(
            lambda: ltn.operating_status is not None,
            "ERROR waiting for the LTN to receive the operating status",
        )
        assert ltn.accepts_dispatch is False
        assert ltn.operating_status.DispatchRefusalReason == reason
        assert scada.auto_state == MainAutoState.LocalControl

        la = scada.services.get_communicator_as_type(CoreNodeNames.leaf_ally, LeafAlly)
        assert la is not None
        given_up: list[AllyGivesUp] = []
        original = la._send_to

        def record(dst, payload, src=None):
            if isinstance(payload, AllyGivesUp):
                given_up.append(payload)
            original(dst, payload, src)

        la._send_to = record  # type: ignore[method-assign]

        ltn.contract_handler.latest_hb = offer(ltn)
        ltn.services.send_threadsafe(
            Message(Src=ltn.node.name, Dst=CoreNodeNames.primary_scada, Payload=ltn.contract_handler.latest_hb)
        )
        await tst.await_for(
            lambda: bool(given_up) and scada.auto_state == MainAutoState.LocalControl,
            "ERROR waiting for the wrapper's AllyGivesUp and the fall back to LocalControl",
        )
        assert given_up[0].Reason.startswith(reason.value)
        assert scada.contract_handler.latest_scada_hb is None


@pytest.mark.asyncio
@pytest.mark.parametrize("pair", sorted(PAIRS))
async def test_accepting_scada_hands_the_offer_to_its_ally(
    request: pytest.FixtureRequest, pair: str
) -> None:
    layout_file, ops_file = PAIRS[pair]
    layout = load_layout(CONFIG / layout_file, CONFIG / ops_file)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=CONFIG / ops_file) as tst:
        tst.start_child1()
        tst.start_parent()
        await tst.await_for(
            lambda: tst.child_to_parent_link.active(),
            "ERROR waiting for scada to ltn link",
        )
        scada = tst.child1_app.scada
        ltn = tst.parent_app.ltn
        await tst.await_for(
            lambda: ltn.operating_status is not None,
            "ERROR waiting for the LTN to receive the operating status",
        )
        assert ltn.accepts_dispatch is True
        la = scada.services.get_communicator_as_type(CoreNodeNames.leaf_ally, LeafAlly)
        assert la is not None
        forwarded: list[SlowDispatchContract] = []
        impl_process = la._impl.process_message

        def record(message):
            if isinstance(message.Payload, SlowDispatchContract):
                forwarded.append(message.Payload)
            return impl_process(message)

        la._impl.process_message = record  # type: ignore[method-assign]

        ltn.contract_handler.latest_hb = offer(ltn)
        ltn.services.send_threadsafe(
            Message(Src=ltn.node.name, Dst=CoreNodeNames.primary_scada, Payload=ltn.contract_handler.latest_hb)
        )
        await tst.await_for(
            lambda: bool(forwarded),
            "ERROR waiting for the offer to reach the family's ally",
        )
