import typing
from pathlib import Path

from gwproactor_test.tree_live_test_helper import TreeLiveTest

from actors.config import ScadaSettings
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

    def __init__(self, **kwargs: typing.Any) -> None:
        kwargs["child_app_settings"] = kwargs.get(
            "child_app_settings",
            ScadaSettings(is_simulated=True),
        )
        kwargs["child2_app_settings"] = kwargs.get(
            "child2_app_settings",
            ScadaSettings(is_simulated=True),
        )
        super().__init__(**kwargs)
