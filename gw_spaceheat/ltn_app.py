import typing
from pathlib import Path
from types import ModuleType
from typing import Optional

from gwproactor import App
from gwproactor import LinkSettings
from gwproactor import Proactor
from gwproactor import ProactorName
from gwproactor.config import MQTTClient
from gwproactor.config import Paths
from gwsproto.data_classes.hardware_layout import HardwareLayout

import actors
from actors.ltn import Ltn
from actors.ltn.config import LtnSettings
from gwsproto.data_classes import house_0_names
from gwsproto.data_classes.house_0_layout import House0Layout
from gwsproto.data_classes.house_0_names import H0N


class LtnApp(App):

    SCADA_MQTT: str = Ltn.SCADA_MQTT

    @classmethod
    def app_settings_type(cls) -> type[LtnSettings]:
        return LtnSettings

    @property
    def settings(self) -> LtnSettings:
        return typing.cast(LtnSettings, super().settings)

    @classmethod
    def prime_actor_type(cls) -> type[Ltn]:
        return Ltn

    @property
    def prime_actor(self) -> Ltn:
        return typing.cast(Ltn, super().prime_actor)

    @property
    def ltn(self) -> Ltn:
        return self.prime_actor

    @classmethod
    def actors_module(cls) -> ModuleType:
        return actors

    @classmethod
    def paths_name(cls) -> str:
        """
        Paths name used for config/log directories.
        Returns 'ltn' so paths use ~/.config/gridworks/ltn/ etc.
        This is the gwproactor framework's hook for setting paths.
        """
        return H0N.ltn

    @classmethod
    def get_settings(
        cls,
        paths_name: Optional[str] = None,
        paths: Optional[Paths] = None,
        settings: Optional[LtnSettings] = None,
        settings_type: Optional[type[LtnSettings]] = None,
        env_file: Optional[str | Path] = None,
    ) -> LtnSettings:
        return typing.cast(
            LtnSettings,
            super().get_settings(
                paths_name=paths_name,
                paths=paths,
                settings=settings,
                settings_type=settings_type,
                env_file=env_file,
            )
        )

    def _load_hardware_layout(self, layout_path: str | Path) -> House0Layout:
        return House0Layout.load(layout_path)

    def _get_name(self, layout: HardwareLayout) -> ProactorName:
        return ProactorName(
            long_name=layout.ltn_g_node_alias,
            short_name=house_0_names.H0N.ltn
        )

    def _get_link_settings(
            self,
            name: ProactorName,
            layout: HardwareLayout,
            brokers: dict[str, MQTTClient]
    ) -> dict[str, LinkSettings]:
        return {
            self.SCADA_MQTT: LinkSettings(
                broker_name=self.SCADA_MQTT,
                peer_long_name=layout.scada_g_node_alias,
                peer_short_name=H0N.primary_scada,
                downstream=True,
            ),
        }

    def _instantiate_proactor(self) -> Proactor:
        proactor = self.sub_types.proactor_type(self, self.config)
        # Note: This is here because LTN loads the web server defined for scada
        #       in the hardware layout
        proactor._web_manager.disable()  # noqa
        return proactor

    @classmethod
    def get_repl_app(
            cls,
            *,
            start: bool = True,
            **kwargs: typing.Any
    ) -> "LtnApp":
        app = typing.cast(LtnApp, LtnApp.make_app_for_cli(**kwargs))
        if start:
            app.run_in_thread()
        return app