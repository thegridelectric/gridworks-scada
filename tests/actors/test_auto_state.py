import time
import uuid
import pytest
from gwproto import Message
from actors import LeafAlly
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import MainAutoState, SlowDispatchContractStatus
from gwsproto.named_types import SlowDispatchContract, SlowContractHeartbeat
from tests.utils.scada_live_test_helper import ScadaLiveTest


@pytest.mark.asyncio
async def test_auto_state_home_alone_to_ltn(request: pytest.FixtureRequest) -> None:
    """Test that auto_state transitions from LocalControl to Ltn when a SlowDispatchContract starts."""
    
    async with ScadaLiveTest(
        request=request,
    ) as tst:
        tst.start_child1() # start primary scada
        tst.start_parent() # start ltn

        await tst.await_for(
            lambda: tst.child_to_parent_link.active(),
            "ERROR waiting for scada to ltn link"
        )
        scada = tst.child1_app.scada
        ltn = tst.parent_app.ltn
        leaf_ally = tst.child1_app.get_communicator_as_type(
                H0N.leaf_ally,
                LeafAlly
            )
        if leaf_ally is None:
            raise Exception("No leaf ally")
        # Verify initial state is LocalControl
        print("Verifying initial state is LocalControl")
        assert scada.auto_state == MainAutoState.LocalControl, f"Expected LocalControl, got {scada.auto_state}"
        
        # Leaf ally will reject contract if it doesn't have forecasts. 
        # It gets forecasts during startup.
        await tst.await_for(
            lambda: leaf_ally.heating_forecast is not None,
            "la never got forecasts!"
        )

        # Ltn creates a slow dispatch contract and hb to send to SCADA
        # Round to the nearest 5 minutes for StartS
        current_time = int(time.time())
        start_s = (current_time // 300) * 300 + 300  # Next 5-minute boundary
        
        contract = SlowDispatchContract(
            ScadaAlias=ltn.layout.scada_g_node_alias,
            StartS=start_s,
            DurationMinutes=60,
            AvgPowerWatts=1000,
            OilBoilerOn=False,
            ContractId=str(uuid.uuid4())
        )
        
        # Create a SlowContractHeartbeat with Created status
        ltn_hb = SlowContractHeartbeat(
            FromNode=ltn.node.name,
            Contract=contract,
            Status=SlowDispatchContractStatus.Created,
            WattHoursUsed=0,
            MessageCreatedMs=int(time.time() * 1000),
            MyDigit=5,
            YourLastDigit=None # First message in chain
        )
        
        ltn.contract_handler.latest_hb = ltn_hb
        ltn.services.send_threadsafe(
                Message(
                    Src=ltn.node.name,
                    Dst=H0N.primary_scada,
                    Payload=ltn.contract_handler.latest_hb,
                )
            )
        
        
        print("Ltn sent creation hb ... waiting for Scada to transition to Ltn")
        await tst.await_for(

            lambda: scada.auto_state == MainAutoState.LeafTransactiveNode,
            "Waiting for auto_state to transition from LocalControl to LeafTransactiveNode",
        )
        
        # Verify state is now Ltn
        assert scada.auto_state == MainAutoState.LeafTransactiveNode, f"Expected Ltn, got {scada.auto_state}"
        print("Scada auto_state successfully transitioned from LocalControl to Ltn")
        
        # Verify contract handler has the contract
        assert scada._contract_handler.latest_scada_hb is not None
        assert scada._contract_handler.latest_scada_hb.Contract.ContractId == contract.ContractId
        assert scada._contract_handler.latest_scada_hb.Status == SlowDispatchContractStatus.Received
        
        # Test that Ltn receives heartbeat back from Scada
        print("Waiting for Ltn to receive heartbeat back from Scada")
        ltn_received_counts = tst.parent_to_child_stats.num_received_by_type

        await tst.await_for(
            lambda: ltn_received_counts['slow.contract.heartbeat'] > 1,
            "Ltn receives slow.contract.heartbeat")

        print(f"Scada auto state is {scada.auto_state}")

        # Verify Ltn received the heartbeat
        print("Ltn received heartbeat from Scada")
        assert ltn.contract_handler.latest_hb.FromNode == H0N.primary_scada
        assert ltn.contract_handler.latest_hb.Status == SlowDispatchContractStatus.Received
        assert ltn.contract_handler.latest_hb.FromNode == H0N.primary_scada
        print(f"Ltn contract status: {ltn.contract_handler.latest_hb.Status}")
