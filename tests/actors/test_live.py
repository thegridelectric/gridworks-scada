import pytest

from tests.utils.scada_live_test_helper import ScadaLiveTest

@pytest.mark.asyncio
async def test_tree_connect(request: pytest.FixtureRequest) -> None:
    """This is a simple wait for ATN and Scada to connect to each other."""
    async with ScadaLiveTest(start_all=True, request=request) as h:
        # Wait for children to connect
        await h.await_for(
            lambda: h.child1_to_child2_link.active()
            and h.child2_to_child1_link.active()
            and h.child_to_parent_link.active(),
            "ERROR waiting children to connect",
        )

@pytest.mark.asyncio
async def test_tree_quiescent(request: pytest.FixtureRequest) -> None:
    """This is a wait for ATN and Scadas to connect and finishing uploading
    the default number of events. """
    async with ScadaLiveTest(start_all=True, request=request) as h:
        await h.await_quiescent_connections()


