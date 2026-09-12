"""An UnValidated scada (no ta.deed beside its layout) refuses every LTN
contract offer with a slow.contract.rejection: the offer starts nothing on
the scada and the LTN drops the pending contract."""

import time
import uuid
from pathlib import Path

import pytest
from gwproactor.config import Paths
from gwproto import Message
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import MainAutoState, SlowDispatchContractStatus, TaValidationState
from gwsproto.named_types import SlowContractHeartbeat, SlowDispatchContract
from sema_to_dc import load_layout
from tests.utils.scada_live_test_helper import ScadaLiveTest

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
    "house0-sim": (
        "gw.house0.sim.layout.json",
        "gw.house0.sim.operational.params.json",
    ),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("pair", sorted(PAIRS))
async def test_unvalidated_scada_rejects_contract_offer(
    request: pytest.FixtureRequest, pair: str
) -> None:
    # The autouse fixture seeds a ValidatedSimulatedAsset deed; remove it so
    # this scada is UnValidated.
    Path(Paths(name="scada").hardware_layout).parent.joinpath("ta-deed.json").unlink()
    layout_file, ops_file = PAIRS[pair]
    layout = load_layout(CONFIG / layout_file, CONFIG / ops_file)

    async with ScadaLiveTest(request=request, layout=layout) as tst:
        tst.start_child1()
        tst.start_parent()

        await tst.await_for(
            lambda: tst.child_to_parent_link.active(),
            "ERROR waiting for scada to ltn link",
        )
        scada = tst.child1_app.scada
        ltn = tst.parent_app.ltn
        assert scada.layout.scada_g_node_alias == layout.scada_g_node_alias
        assert ltn.layout.scada_g_node_alias == layout.scada_g_node_alias
        assert scada.services.validation_state == TaValidationState.UnValidated
        assert scada.auto_state == MainAutoState.LocalControl

        current_time = int(time.time())
        start_s = (current_time // 300) * 300 + 300
        contract = SlowDispatchContract(
            ScadaAlias=ltn.layout.scada_g_node_alias,
            StartS=start_s,
            DurationMinutes=60,
            AvgPowerWatts=1000,
            OilBoilerOn=False,
            ContractId=str(uuid.uuid4()),
        )
        ltn_hb = SlowContractHeartbeat(
            FromNode=ltn.node.name,
            Contract=contract,
            Status=SlowDispatchContractStatus.Created,
            WattHoursUsed=0,
            MessageCreatedMs=int(time.time() * 1000),
            MyDigit=5,
            YourLastDigit=None,
        )
        ltn.contract_handler.latest_hb = ltn_hb
        ltn.services.send_threadsafe(
            Message(
                Src=ltn.node.name,
                Dst=H0N.primary_scada,
                Payload=ltn.contract_handler.latest_hb,
            )
        )

        # The LTN learns why: its pending offer is dropped on the rejection.
        await tst.await_for(
            lambda: ltn.contract_handler.latest_hb is None,
            "Waiting for the LTN to receive the scada's rejection",
        )
        assert scada.auto_state == MainAutoState.LocalControl
        assert scada._contract_handler.latest_scada_hb is None
