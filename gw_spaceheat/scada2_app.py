import typing
from typing import Any, Optional
from pathlib import Path
from types import ModuleType

from gwproactor import ProactorSettings
from gwproactor.app import App
from gwproactor.config import MQTTClient
from gwproactor.config.links import LinkSettings
from gwproactor.config.proactor_config import ProactorName
from gwproactor.external_watchdog import SystemDWatchdogCommandBuilder
from gwproactor.persister import TimedRollingFilePersister
from gwproto import HardwareLayout

import actors
from actors import SecondaryScada
from actors import ScadaInterface
from actors.config import ScadaSettings
from sema_to_dc import load_layout
from actors.scada import ScadaCodecFactory
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.names.core.node_names import CoreNodeNames
from clock import Clock, build_clock
from scada_app_interface import ScadaAppInterface


class Scada2App(App, ScadaAppInterface):
    LOCAL_MQTT: str = ScadaCodecFactory.LOCAL_MQTT

    @classmethod
    def app_settings_type(cls) -> type[ScadaSettings]:
        return ScadaSettings

    @classmethod
    def prime_actor_type(cls) -> type[SecondaryScada]:
        return SecondaryScada

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

    def _load_hardware_layout(self, layout_path: str | Path) -> HydronicLayout:
        """Load the runtime layout. A sema-authored static artifact (its
        TypeName names a sema layout type) is assembled with the home's
        operational-params artifact; a runtime-shaped layout file loads
        directly."""
        return load_layout(
            layout_path, Path(self.settings.paths.operational_params)
        )

    def _get_name(self, layout: HardwareLayout) -> ProactorName:
        return ProactorName(
            long_name=typing.cast(HydronicLayout, layout).scada2_g_node_name(),
            short_name=CoreNodeNames.secondary_scada
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
                peer_short_name=CoreNodeNames.primary_scada,
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

    def __init__(self, *, clock: Optional[Clock] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._clock = clock if clock is not None else build_clock(
            self.settings.clock_source, self.is_simulated, self.settings.gridworks_mqtt
        )

    @property
    def settings(self) -> ScadaSettings:
        return typing.cast(ScadaSettings, super().settings)

    @property
    def clock(self) -> Clock:
        return self._clock

    @property
    def prime_actor(self) -> SecondaryScada:
        return typing.cast(SecondaryScada, super().prime_actor)

    @property
    def scada(self) -> ScadaInterface:
        return self.prime_actor

    def upstream_is_send_capable(self) -> bool:
        return self.proactor.links.upstream_link.active_for_send()

    @property
    def hardware_layout(self) -> HydronicLayout:
        return typing.cast(HydronicLayout, super().hardware_layout)
