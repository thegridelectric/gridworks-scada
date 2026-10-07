import typing
from typing import Any, Optional
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
from gwsproto.data_classes.hydronic_layout import HydronicLayout

import actors
from actors.scada import Scada
from actors.scada_interface import ScadaInterface
from actors.config import ScadaSettings
from actors.scada_data import load_operational_params
from sema_to_dc import load_layout
from gwsproto.names.core.node_names import CoreNodeNames
from clock import Clock, build_clock
from weather_source import WeatherSource, build_weather_source
from scada_app_interface import ScadaAppInterface
from universe import assert_universe_coherence


@typing.runtime_checkable
class DerivedChannelCreator(typing.Protocol):
    """An actor that creates derived channels says which, so boot can hold
    the layout's CreatedByNodeName to an actor that really makes the
    channel."""

    def derived_channels_created(self) -> set[str]: ...


class ScadaApp(App, ScadaAppInterface):
    LTN_MQTT: str = ScadaInterface.LTN_MQTT
    LOCAL_MQTT: str = ScadaInterface.LOCAL_MQTT
    ADMIN_MQTT: str = ScadaInterface.ADMIN_MQTT

    @classmethod
    def app_settings_type(cls) -> type[ScadaSettings]:
        return ScadaSettings

    def __init__(
        self,
        *,
        clock: Optional[Clock] = None,
        weather_source: Optional[WeatherSource] = None,
        **kwargs: Any,
    ) -> None:
        """clock: injected only by tests (a ManualClock); a box builds its
        clock from settings.clock_source."""
        super().__init__(**kwargs)
        self._clock = clock if clock is not None else build_clock(
            self.settings.clock_source, self.is_simulated, self.settings.gridworks_mqtt
        )
        self._weather_source = weather_source if weather_source is not None else build_weather_source(
            self.settings.weather_source,
            load_operational_params(self.settings),
            Path(self.settings.paths.config_dir),
            self.settings.weather_api_url,
            self.settings.weather_pull_timeout_s,
            self._clock,
            self.settings.logging.base_log_name,
        )

    @property
    def settings(self) -> ScadaSettings:
        return typing.cast(ScadaSettings, self._settings)

    def instantiate(self) -> "ScadaApp":
        super().instantiate()
        self.assert_derived_creators()
        return self

    def assert_derived_creators(self) -> None:
        """Every derived channel the layout names a scada actor creator of is
        one that actor claims, and every claim is a channel the layout names
        that actor creator of. A channel with a named creator that nothing
        makes never reaches the snapshot or the report; the layout is refused
        at boot instead. Disabled derived channels are outside the check."""
        layout = self.hardware_layout
        proactor = self.raw_proactor
        actor_names = set(proactor.get_communicator_names())
        claimed: dict[str, str] = {}
        for name in actor_names:
            actor = proactor.get_communicator(name)
            if isinstance(actor, DerivedChannelCreator):
                for channel in actor.derived_channels_created():
                    claimed[channel] = name
        declared = {
            dc.Name: dc.CreatedByNodeName
            for dc in layout.derived_channels.values()
            if dc.CreatedByNodeName in actor_names
            and not layout.channel_disabled(dc.Name)
        }
        problems = [
            f"{channel} is created by {creator}, which does not claim it"
            for channel, creator in declared.items()
            if claimed.get(channel) != creator
        ] + [
            f"{channel} is claimed by {actor}, which the layout does not name its creator"
            for channel, actor in claimed.items()
            if declared.get(channel) != actor
            and not (
                channel in layout.derived_channels and layout.channel_disabled(channel)
            )
        ]
        if problems:
            raise ValueError("Derived channel creators: " + "; ".join(problems))

    @property
    def clock(self) -> Clock:
        return self._clock

    @property
    def weather_source(self) -> WeatherSource:
        return self._weather_source

    @classmethod
    def prime_actor_type(cls) -> type[Scada]:
        return Scada

    @property
    def prime_actor(self) -> Scada:
        return typing.cast(Scada, super().prime_actor)


    @property
    def scada(self) -> Scada:
        return self.prime_actor

    def upstream_is_send_capable(self) -> bool:
        return self.proactor.links.upstream_link.active_for_send()

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
        layout: Optional[HydronicLayout] = None,
        env_file: Optional[str | Path] = None,
        dry_run: bool = False,
        add_screen_handler: bool = True,
    ) -> "ScadaApp":
        app = typing.cast(
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
        app.assert_universe_coherence()
        return app

    def assert_universe_coherence(self) -> None:
        """Refuse to run if the layout's GNode universe disagrees with the broker.

        The universe-guardrail (universe-guardrail spoke): a GNode may only talk
        on a broker in its own universe. Checked at the real boot path (here, via
        `cli.py run`/`main`), not in generic construction, so tests that load a
        layout from one universe against a localhost broker are unaffected."""
        layout = self.hardware_layout
        assert_universe_coherence(
            {
                "scada": layout.scada_g_node_alias,
                "ltn": layout.ltn_g_node_alias,
                "terminal_asset": layout.terminal_asset_g_node_alias,
            },
            self.settings.gridworks_mqtt.host,
        )

    def _load_hardware_layout(self, layout_path: str | Path) -> HydronicLayout:
        """Load the runtime layout. A sema-authored static artifact (its TypeName
        names a sema layout type) is assembled with the home's operational-params
        artifact; a runtime-shaped layout file loads directly."""
        return load_layout(
            layout_path, Path(self.settings.paths.operational_params)
        )

    @property
    def hardware_layout(self) -> HydronicLayout:
        return typing.cast(HydronicLayout, self.config.layout)

    def _get_name(self, layout: HydronicLayout) -> ProactorName:
        return ProactorName(
            long_name=layout.scada_g_node_alias,
            short_name=CoreNodeNames.primary_scada
        )

    def _get_link_settings(
            self,
            name: ProactorName,
            layout: HydronicLayout,
            brokers: dict[str, MQTTClient]
    ) -> dict[str, LinkSettings]:
        return {
            self.LTN_MQTT: LinkSettings(
                broker_name=self.LTN_MQTT,
                peer_long_name=layout.ltn_g_node_alias,
                peer_short_name=CoreNodeNames.ltn,
                upstream=True,
            ),
            self.LOCAL_MQTT: LinkSettings(
                broker_name=self.LOCAL_MQTT,
                peer_long_name=typing.cast(HydronicLayout, layout).scada2_g_node_name(),
                peer_short_name=CoreNodeNames.secondary_scada,
                downstream=True,
            ),
            self.ADMIN_MQTT: LinkSettings(
                broker_name=self.ADMIN_MQTT,
                peer_long_name=CoreNodeNames.admin,
                peer_short_name=CoreNodeNames.admin,
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

