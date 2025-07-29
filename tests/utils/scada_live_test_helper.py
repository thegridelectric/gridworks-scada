import typing
from typing import Optional

from pathlib import Path

from gwproactor_test.instrumented_proactor import MinRangeTuple
from gwproactor_test.tree_live_test_helper import TreeLiveTest

from actors.config import ScadaSettings
from data_classes.house_0_layout import House0Layout
from tests.conftest import TEST_HARDWARE_LAYOUT_PATH
from tests.atn.atn_app import AtnApp
from scada2_app import Scada2App
from scada_app import ScadaApp


class ScadaLiveTest(TreeLiveTest):
    UPLOADER_LONG_NAME = "test_uploader"

    @classmethod
    def parent_app_type(cls) -> type[AtnApp]:
        return AtnApp

    @property
    def parent_app(self) -> AtnApp:
        return typing.cast(AtnApp, self._parent_app)

    @classmethod
    def child_app_type(cls) -> type[ScadaApp]:
        return ScadaApp

    @property
    def child_app(self) -> ScadaApp:
        return typing.cast(ScadaApp, self._child_app)

    @property
    def child1_app(self) -> ScadaApp:
        return self.child_app

    @classmethod
    def child2_app_type(cls) -> type[Scada2App]:
        return Scada2App

    @property
    def child2_app(self) -> Scada2App:
        return typing.cast(Scada2App, self._child2_app)

    @classmethod
    def test_layout_path(cls) -> Path:
        return TEST_HARDWARE_LAYOUT_PATH

    def __init__(self,
        *,
        layout: Optional[House0Layout] = None,
        child_layout: Optional[House0Layout] = None,
        child1_layout: Optional[House0Layout] = None,
        child2_layout: Optional[House0Layout] = None,
        parent_layout: Optional[House0Layout] = None,
        **kwargs: typing.Any
    ) -> None:
        kwargs["child_app_settings"] = kwargs.get(
            "child_app_settings",
            ScadaSettings(is_simulated=True),
        )
        kwargs["child2_app_settings"] = kwargs.get(
            "child2_app_settings",
            ScadaSettings(is_simulated=True),
        )
        super().__init__(
            layout=layout,
            child_layout=child_layout,
            child1_layout=child1_layout,
            child2_layout=child2_layout,
            parent_layout=parent_layout,
            **kwargs
        )

    # noinspection PyMethodMayBeStatic
    def default_quiescent_total_children_events(self) -> int:
        return sum(
            [
                4,  # child2 startup, connect, subscribe, peer active
                1,  # child1 startup
                6,  # child1 (parent, child2, admin) x (connect, subscribe)
                2,  # child1 (parent, child2) x peer active
            ]
        )

    # noinspection PyMethodMayBeStatic
    def default_quiesecent_parent_pending(
        self,
        exp_child_persists: Optional[int | MinRangeTuple] = None,
        exp_total_children_events: Optional[int] = None,
    ) -> int:
        return 0  # ATN does not attempt to forward child events.

    # noinspection PyMethodMayBeStatic
    def default_quiesecent_parent_persists(
        self,
        exp_parent_pending: Optional[int | MinRangeTuple] = None,
        exp_child_persists: Optional[int | MinRangeTuple] = None,
    ) -> int:
        return 4 # startup, connect, subscribed, child1 active; ATN does not
                 #   persist child events

    async def await_parent_at_rest(
        self,
        *,
        exp_parent_pending: int | MinRangeTuple,
        exp_parent_persists: Optional[int | MinRangeTuple] = None,
        exp_total_children_events: Optional[int] = None,  # noqa: ARG002
        exact: bool = False,
        caller_depth: int = 4,
    ) -> None:
        await super().await_parent_at_rest(
            exp_parent_pending=exp_parent_pending,
            exp_parent_persists=exp_parent_persists,
            exact=exact,
            caller_depth=caller_depth + 1,
        )
        def _child_events_received() -> int:
            rcv = 0
            scada_link_stats = self.parent.stats.link(self.parent.downstream_client)
            for event_src_dict in scada_link_stats.event_counts.values():
                rcv += sum(event_src_dict.values())
            return rcv

        await self.await_for(
            lambda: _child_events_received() >= exp_total_children_events,
            (
                f"ERROR waiting for ATN to receive {exp_total_children_events} "
                "told child events"
            ),
            caller_depth=caller_depth,
        )
