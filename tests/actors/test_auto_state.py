import time
import uuid
import pytest
from gwproto import Message
from actors import AtomicAlly
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import MainAutoState, SlowDispatchContractStatus
from gwsproto.named_types import SlowDispatchContract, SlowContractHeartbeat
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
        aa = h.child1_app.get_communicator_as_type(
                H0N.leaf_ally,
                AtomicAlly
            )
        if aa is None:
            raise Exception("No aa")
        # Verify initial state is HomeAlone
        print("Verifying initial state is HomeAlone")
        assert scada.auto_state == MainAutoState.HomeAlone, f"Expected HomeAlone, got {scada.auto_state}"
        
        # atomic ally will reject contract if it doesn't have forecasts. 
        # It gets forecasts during startup.
        await h.await_for(
            lambda: aa.heating_forecast is not None,
            "aa never got forecasts!"
        )

        # Atn creates a slow dispatch contract and hb to send to SCADA
        # Round to the nearest 5 minutes for StartS
        current_time = int(time.time())
        start_s = (current_time // 300) * 300 + 300  # Next 5-minute boundary
        
        contract = SlowDispatchContract(
            ScadaAlias=atn.layout.scada_g_node_alias,
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
            Status=SlowDispatchContractStatus.Created,
            WattHoursUsed=0,
            MessageCreatedMs=int(time.time() * 1000),
            MyDigit=5,
            YourLastDigit=None # First message in chain
        )
        
        atn.contract_handler.latest_hb = atn_hb
        atn.services.send_threadsafe(
                Message(
                    Src=atn.node.name,
                    Dst=H0N.primary_scada,
                    Payload=atn.contract_handler.latest_hb,
                )
            )
        
        
        print("Atn sent creation hb ... waiting for Scada to transition to Atn")
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
        assert scada._contract_handler.latest_scada_hb.Status == SlowDispatchContractStatus.Received
        
        # Test that ATN receives heartbeat back from Scada
        print("Waiting for ATN to receive heartbeat back from Scada")
        atn_received_counts = h.parent_to_child_stats.num_received_by_type

        await h.await_for(
            lambda: atn_received_counts['slow.contract.heartbeat'] > 1,
            "Atn receives slow.contract.heartbeat")

        print(f"Scada auto state is {scada.auto_state}")

        # Verify ATN received the heartbeat
        print("ATN received heartbeat from Scada")
        assert atn.contract_handler.latest_hb.FromNode == H0N.primary_scada
        assert atn.contract_handler.latest_hb.Status == SlowDispatchContractStatus.Received
        assert atn.contract_handler.latest_hb.FromNode == H0N.primary_scada
        print(f"ATN contract status: {atn.contract_handler.latest_hb.Status}")

        # hb = SlowContractHeartbeat(
        #     FromNode=atn.node.name,
        #     Contract=atn.contract_handler.latest_hb.Contract,
        #     PreviousStatus=atn.contract_handler.latest_hb.Status,
        #     Status=SlowDispatchContractStatus.TerminatedByAtn,
        #     Cause="Atn testing termination",
        #     MessageCreatedMs=int(time.time() * 1000),
        #     MyDigit=2,
        #     YourLastDigit=atn.contract_handler.latest_hb.MyDigit,
        # )
        # atn.contract_handler.latest_hb = None

        # atn.services.send_threadsafe(
        #         Message(
        #             Src=atn.node.name,
        #             Dst=H0N.primary_scada,
        #             Payload=hb,
        #         )
        #     )
        
        # print("Atn sent termination hb ... waiting for scada to transition to HomeALone")
        # await h.await_for(

        #     lambda: scada.auto_state == MainAutoState.HomeAlone,
        #     "Waiting for auto_state to transition from Atn to HomeAlone",
        # )
        # That's funny: Ack! Haven't thought through termination by atn
        
