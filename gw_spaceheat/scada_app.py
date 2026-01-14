import typing
from typing import Optional
from pathlib import Path
from types import ModuleType

from gwproactor import CodecFactory
from gwproactor import ProactorSettings
from gwproactor.app import App
from gwproactor.app import SubTypes
from gwproactor.config import MQTTClient
from gwproactor.config import Paths
from gwproactor.config.links import LinkSettings
from gwproactor.config.proactor_config import ProactorName
from gwproactor.external_watchdog import SystemDWatchdogCommandBuilder
from gwproactor.persister import TimedRollingFilePersister
from gwproto import HardwareLayout

import actors
from actors.scada import Scada
from actors.scada_interface import ScadaInterface
from actors.config import ScadaSettings
from gwsproto.data_classes import house_0_names
from gwsproto.data_classes.house_0_layout import House0Layout
from gwsproto.data_classes.house_0_names import H0N
from scada_app_interface import ScadaAppInterface


class ScadaApp(App, ScadaAppInterface):
    ATN_MQTT: str = ScadaInterface.ATN_MQTT
    LOCAL_MQTT: str = ScadaInterface.LOCAL_MQTT
    ADMIN_MQTT: str = ScadaInterface.ADMIN_MQTT

    @classmethod
    def app_settings_type(cls) -> type[ScadaSettings]:
        return ScadaSettings

    @property
    def settings(self) -> ScadaSettings:
        return typing.cast(ScadaSettings, self._settings)

    @classmethod
    def prime_actor_type(cls) -> type[Scada]:
        return Scada

    @property
    def prime_actor(self) -> Scada:
        return typing.cast(Scada, super().prime_actor)


    @property
    def scada(self) -> Scada:
        return self.prime_actor

    @classmethod
    def actors_module(cls) -> ModuleType:
        return actors

    @classmethod
    def paths_name(cls) -> str:
        return "scada"

    # Scada uses dotenv.find_dotenv($PWD/.env) in multiple clis and also
    # internally in at least two places (updating env vars and in eGauge
    # "be_the_proxy()"). We don't expect this function to be called, but we
    # make it consistent in case it is called.
    @classmethod
    def default_env_path(cls) -> Path:
        return Path(".env")

    @classmethod
    def get_settings(
        cls,
        paths_name: Optional[str] = None,
        paths: Optional[Paths] = None,
        settings: Optional[ScadaSettings] = None,
        settings_type: Optional[type[ScadaSettings]] = None,
        env_file: Optional[str | Path] = None,
    ) -> ScadaSettings:
        return typing.cast(
            ScadaSettings,
            super().get_settings(
                paths_name=paths_name,
                paths=paths,
                settings=settings,
                settings_type=settings_type,
                env_file=env_file,
            )
        )

    @classmethod
    def make_app_for_cli(  # noqa: PLR0913
        cls,
        *,
        app_settings: ScadaSettings,
        codec_factory: Optional[CodecFactory] = None,
        sub_types: Optional[SubTypes] = None,
        layout: Optional[HardwareLayout] = None,
        env_file: Optional[str | Path] = None,
        dry_run: bool = False,
        add_screen_handler: bool = True,
    ) -> "ScadaApp":
        return typing.cast(
            ScadaApp,
            super().make_app_for_cli(
                app_settings=app_settings,
                codec_factory=codec_factory,
                sub_types=sub_types,
                layout=layout,
                env_file=env_file,
                dry_run=dry_run,
                add_screen_handler=add_screen_handler,
            )
        )

    def _load_hardware_layout(self, layout_path: str | Path) -> House0Layout:
        return House0Layout.load(layout_path)

    @property
    def hardware_layout(self) -> House0Layout:
        return typing.cast(House0Layout, self.config.layout)

    def _get_name(self, layout: HardwareLayout) -> ProactorName:
        return ProactorName(
            long_name=layout.scada_g_node_alias,
            short_name=house_0_names.H0N.primary_scada
        )

    def _get_link_settings(
            self,
            name: ProactorName,
            layout: HardwareLayout,
            brokers: dict[str, MQTTClient]
    ) -> dict[str, LinkSettings]:
        return {
            self.ATN_MQTT: LinkSettings(
                broker_name=self.ATN_MQTT,
                peer_long_name=layout.atn_g_node_alias,
                peer_short_name=H0N.ltn,
                upstream=True,
            ),
            self.LOCAL_MQTT: LinkSettings(
                broker_name=self.LOCAL_MQTT,
                peer_long_name=typing.cast(House0Layout, layout).scada2_gnode_name(),
                peer_short_name=H0N.secondary_scada,
                downstream=True,
            ),
            self.ADMIN_MQTT: LinkSettings(
                broker_name=self.ADMIN_MQTT,
                peer_long_name=H0N.admin,
                peer_short_name=H0N.admin,
                link_subscription_short_name=name.publication_name
            ),
        }

    def _make_persister(self, settings: ProactorSettings) -> TimedRollingFilePersister:
        return TimedRollingFilePersister(
            settings.paths.event_dir,
            max_bytes=settings.persister.max_bytes,
            pat_watchdog_args=SystemDWatchdogCommandBuilder.pat_args(
                str(settings.paths.name)
            ),
        )

