import logging
import time
import uuid
import pytest
from gwproto import Message
from data_classes.house_0_names import H0N
from enums import MainAutoState, ContractStatus
from named_types import SlowDispatchContract, SlowContractHeartbeat
from tests.utils.scada_live_test_helper import ScadaLiveTest


@pytest.mark.asyncio
async def test_auto_state_home_alone_to_atn(request: pytest.FixtureRequest) -> None:
    """Test that auto_state transitions from HomeAlone to Atn when a SlowDispatchContract starts."""
    
    async with ScadaLiveTest(
        request=request,
    ) as h:
        h.start_child1() # start primary scada
        h.start_parent() # start atn

        await h.await_for(
            lambda: h.child_to_parent_link.active(),
            "ERROR waiting for scada to atn link"
        )
        scada = h.child1_app.scada
        atn = h.parent_app.atn
        # Verify initial state is HomeAlone
        print("Verifying initial state is HomeAlone")
        assert scada.auto_state == MainAutoState.HomeAlone, f"Expected HomeAlone, got {scada.auto_state}"
        
        # Atn creates a slow dispatch contract and hb to send to SCADA
        # Round to the nearest 5 minutes for StartS
        current_time = int(time.time())
        start_s = (current_time // 300) * 300 + 300  # Next 5-minute boundary
        
        contract = SlowDispatchContract(
            ScadaAlias=scada.layout.scada_g_node_alias,
            StartS=start_s,
            DurationMinutes=60,
            AvgPowerWatts=1000,
            OilBoilerOn=False,
            ContractId=str(uuid.uuid4())
        )
        
        # Create a SlowContractHeartbeat with Created status
        atn_hb = SlowContractHeartbeat(
            FromNode=atn.node.name,
            Contract=contract,
            PreviousStatus=ContractStatus.Created,
            Status=ContractStatus.Created,
            WattHoursUsed=0,
            MessageCreatedMs=int(time.time() * 1000),
            MyDigit=5,
            YourLastDigit=0
        )
        
        atn.contract_handler.latest_hb = atn_hb
        atn.services.send_threadsafe(
                Message(
                    Src=atn.node.name,
                    Dst=H0N.primary_scada,
                    Payload=atn.contract_handler.latest_hb,
                )
            )
        
        
        print("Atn sent hb ... waiting for state transition to Atn")
        await h.await_for(

            lambda: scada.auto_state == MainAutoState.Atn,
            "Waiting for auto_state to transition from HomeAlone to Atn",
        )
        
        # Verify state is now Atn
        assert scada.auto_state == MainAutoState.Atn, f"Expected Atn, got {scada.auto_state}"
        print("Scada auto_state successfully transitioned from HomeAlone to Atn")
        
        # Verify contract handler has the contract
        assert scada._contract_handler.latest_scada_hb is not None
        assert scada._contract_handler.latest_scada_hb.Contract.ContractId == contract.ContractId
        assert scada._contract_handler.latest_scada_hb.Status == ContractStatus.Received
        
        # Test that ATN receives heartbeat back from Scada
        print("Waiting for ATN to receive heartbeat back from Scada")
        atn_received_counts = h.parent_to_child_stats.num_received_by_type

        await h.await_for(
            lambda: atn_received_counts['slow.contract.heartbeat'] > 1,
            "Atn receives slow.contract.heartbeat")

        print(f"Scada auto state is {scada.auto_state}")
        # Wait for ATN to receive the response heartbeat from Scada
        # await h.await_for(
        #     lambda: (atn.contract_handler.latest_hb is not None 
        #             and atn.contract_handler.latest_hb.Status != ContractStatus.Created
        #             and atn.contract_handler.latest_hb.FromNode == H0N.primary_scada),
        #     "Waiting for ATN to receive heartbeat response from Scada"
        # )
        
        # Verify ATN received the heartbeat
        print("ATN received heartbeat from Scada")
        assert atn.contract_handler.latest_hb.FromNode == H0N.primary_scada
        assert atn.contract_handler.latest_hb.Status == ContractStatus.Received
        assert atn.contract_handler.latest_hb.FromNode == H0N.primary_scada
        print(f"ATN contract status: {atn.contract_handler.latest_hb.Status}")