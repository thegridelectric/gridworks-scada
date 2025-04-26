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
from gwproto import HardwareLayout

import actors
from actors.atn import Atn
from atn import AtnSettings
from data_classes import house_0_names
from data_classes.house_0_layout import House0Layout
from data_classes.house_0_names import H0N


class AtnApp(App):

    SCADA_MQTT = "scada_mqtt"

    @classmethod
    def app_settings_type(cls) -> type[AtnSettings]:
        return AtnSettings

    @classmethod
    def prime_actor_type(cls) -> type[Atn]:
        return Atn

    @classmethod
    def actors_module(cls) -> ModuleType:
        return actors

    @classmethod
    def paths_name(cls) -> str:
        return "scada"

    @classmethod
    def get_settings(
        cls,
        paths_name: Optional[str] = None,
        paths: Optional[Paths] = None,
        settings: Optional[AtnSettings] = None,
        settings_type: Optional[type[AtnSettings]] = None,
        env_file: Optional[str | Path] = None,
    ) -> AtnSettings:
        return typing.cast(
            AtnSettings,
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
            long_name=layout.atn_g_node_alias,
            short_name=house_0_names.H0N.atn
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
        proactor = self.sub_types.proactor_type(self.config)
        # Note: This is here because ATN loads the web server defined for scada
        #       in the hardware layout
        proactor._web_manager.disable()  # noqa
        return proactor
