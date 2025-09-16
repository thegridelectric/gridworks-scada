import typing
from typing import Any
from pathlib import Path
from types import ModuleType

from gwproactor import ProactorSettings
from gwproactor.app import App, ActorConfig
from gwproactor.config import MQTTClient
from gwproactor.config.links import LinkSettings
from gwproactor.config.proactor_config import ProactorName
from gwproactor.external_watchdog import SystemDWatchdogCommandBuilder
from gwproactor.persister import TimedRollingFilePersister
from gwproto import HardwareLayout

import actors
from actors import Parentless
from actors import ScadaInterface
from actors.config import ScadaSettings
from actors.scada import ScadaCodecFactory
from gwsproto.data_classes import house_0_names
from gwsproto.data_classes.house_0_layout import House0Layout
from gwsproto.data_classes.house_0_names import H0N
from scada_app_interface import ScadaAppInterface


class Scada2App(App, ScadaAppInterface):
    LOCAL_MQTT: str = ScadaCodecFactory.LOCAL_MQTT

    @classmethod
    def app_settings_type(cls) -> type[ScadaSettings]:
        return ScadaSettings

    @classmethod
    def prime_actor_type(cls) -> type[Parentless]:
        return Parentless

    @classmethod
    def actors_module(cls) -> ModuleType:
        return actors

    @classmethod
    def paths_name(cls) -> str:
        return "scada2"

    # We don't expect this function to be called, but we
    # make it consistent in case it is called. See similar note in Scada.
    @classmethod
    def default_env_path(cls) -> Path:
        return Path(".env")

    def _load_hardware_layout(self, layout_path: str | Path) -> House0Layout:
        return House0Layout.load(layout_path)

    def _get_name(self, layout: HardwareLayout) -> ProactorName:
        return ProactorName(
            long_name=typing.cast(House0Layout, layout).scada2_gnode_name(),
            short_name=house_0_names.H0N.secondary_scada
        )

    def _get_link_settings(
            self,
            name: ProactorName,
            layout: HardwareLayout,
            brokers: dict[str, MQTTClient]
    ) -> dict[str, LinkSettings]:
        return {
            self.LOCAL_MQTT: LinkSettings(
                broker_name=self.LOCAL_MQTT,
                peer_long_name=self.hardware_layout.scada_g_node_alias,
                peer_short_name=H0N.primary_scada,
                upstream=True,
            )
        }

    def _make_persister(self, settings: ProactorSettings) -> TimedRollingFilePersister:
        return TimedRollingFilePersister(
            settings.paths.event_dir,
            max_bytes=settings.persister.max_bytes,
            pat_watchdog_args=SystemDWatchdogCommandBuilder.pat_args(
                str(settings.paths.name)
            ),
        )


    @classmethod
    def get_settings(cls, *args: Any, **kwargs: Any) -> ScadaSettings:
        return typing.cast(
            ScadaSettings,
            super().get_settings(*args, **kwargs)
        )

    @property
    def settings(self) -> ScadaSettings:
        return typing.cast(ScadaSettings, super().settings)

    @property
    def prime_actor(self) -> Parentless:
        return typing.cast(Parentless, super().prime_actor)

    @property
    def scada(self) -> ScadaInterface:
        return self.prime_actor

    @property
    def hardware_layout(self) -> House0Layout:
        return typing.cast(House0Layout, super().hardware_layout)
