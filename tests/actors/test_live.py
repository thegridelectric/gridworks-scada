import pytest

from tests.utils.scada_live_test_helper import ScadaLiveTest

@pytest.mark.asyncio
async def test_tree_connect(request: pytest.FixtureRequest) -> None:
    """This is a simple wait for ATN and Scada to connect to each other."""
    async with ScadaLiveTest(
        start_child1=True,
        start_child2=True,
        start_parent=True,
        request=request,
        child_verbose=True,
    ) as h:
        child1 = h.child
        link1to2 = child1.links.link(child1.downstream_client)
        link1toAtn = child1.links.link(child1.upstream_client)

        child2 = h.child2
        link2to1 = child2.links.link(child2.upstream_client)

        # Wait for children to connect
        await h.await_for(
            lambda: link1to2.active()
            and link2to1.active()
            and link1toAtn.active(),
            "ERROR waiting children to connect",
        )

@pytest.mark.asyncio
async def test_tree_quiescent(request: pytest.FixtureRequest) -> None:
    """This is a wait for ATN and Scadas to connect and finishing uploading
    the default number of events. """
    async with ScadaLiveTest(
        start_child1=True,
        start_child2=True,
        start_parent=True,
        request=request,
        child_verbose=True,
    ) as h:
        await h.await_quiescent_connections()


