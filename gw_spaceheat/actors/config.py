import logging
from pathlib import Path
from typing import Any, Self

from pydantic import Field, ValidationInfo, field_validator
from gwproactor import AppSettings
from gwproactor.config.mqtt import TLSInfo
from pydantic import BaseModel

from gwsproto.names.core.node_names import CoreNodeNames
from clock import ClockSource
from gwproactor.config import MQTTClient, Paths
from pydantic_settings import SettingsConfigDict

# The deployed config dir holds the two authored artifacts under fixed names,
# beside each other: proactor already fixes the layout as hardware-layout.json
# (gwproactor.config.paths.DEFAULT_LAYOUT_FILE), and the operational params sit
# next to it. Deliberately NOT the sema on-disk filename grammar
# (<subject>-<type.name>-<version>.json): that grammar exists so an eventstore
# key carries identity, whereas here the path is known and identity is read from
# the payload's TypeName (see sema_to_dc.load_layout, which dispatches on it).
DEFAULT_OPS_PARAMS_FILE = Path("operational-params.json")
# The home's ta.deed instance, beside the hardware layout; absent until a
# TaValidator has issued one.
DEFAULT_TA_DEED_FILE = Path("ta-deed.json")

DEFAULT_TEST_LAYOUT = (
    Path(__file__).resolve()
    .parents[2]   # adjust depth as needed
    / "tests"
    / "config"
    / "gw.nolan.layout.json"
)


DEFAULT_MAX_EVENT_BYTES: int = 500 * 1024 * 1024

# A power meter channel with no read that returned a value for this long is
# lost.
POWER_METER_LOST_AFTER_S: float = 10

class PersisterSettings(BaseModel):
    max_bytes: int = DEFAULT_MAX_EVENT_BYTES


class ScadaPaths(Paths):
    """Paths plus the scada-family locations: the home's authored
    operational-params artifact, defaulting to the file beside the hardware
    layout in the same folder."""

    operational_params: str | Path = Field(default="", validate_default=True)
    # The home's ta.deed instance (ScadaAppInterface.validation_state reads
    # it; UnValidated when absent). Defaults beside the hardware layout.
    tadeed: str | Path = Field(default="", validate_default=True)

    @field_validator("operational_params")
    @classmethod
    def get_operational_params(cls, v: Any, info: ValidationInfo) -> Path:
        if not v:
            v = Path(info.data["hardware_layout"]).parent / DEFAULT_OPS_PARAMS_FILE
        return Path(v)

    @field_validator("tadeed")
    @classmethod
    def get_tadeed(cls, v: Any, info: ValidationInfo) -> Path:
        if not v:
            v = Path(info.data["hardware_layout"]).parent / DEFAULT_TA_DEED_FILE
        return Path(v)

    def duplicate(
        self,
        *,
        exclude_unset: bool = True,
        exclude_defaults: bool = True,
        exclude: set[str] | None = None,
        **kwargs: Any,
    ) -> "ScadaPaths":
        # the gwproactor version returns base Paths, dropping subclass fields
        fields = self.model_dump(
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude=exclude,
        )
        fields.update(**kwargs)
        return ScadaPaths(**fields)


class ScadaPathsSettings(AppSettings):
    """AppSettings whose paths are ScadaPaths. update_paths_name and
    with_paths are overridden because the gwproactor versions rebuild (or
    accept) base Paths, which would silently drop the scada-family fields."""

    paths: ScadaPaths = Field(default_factory=ScadaPaths, validate_default=True)

    def update_paths_name(self, name: str | Path) -> Self:
        self.paths = ScadaPaths(
            name=name, **self.paths.model_dump(exclude={"name"}, exclude_unset=True)
        )
        self.update_tls_paths()
        return self

    def with_paths(self, *, paths: Paths | None = None, **kwargs: Any) -> Self:
        # an incoming base Paths replaces self.paths wholesale; carry the
        # explicitly-set scada-family fields (e.g. an env-pinned
        # operational_params) across, and re-derive the unset ones
        if paths is not None and not isinstance(paths, ScadaPaths):
            carried = self.paths.model_dump(
                include={"operational_params"}, exclude_unset=True
            )
            paths = ScadaPaths(
                **{**paths.model_dump(exclude_unset=True), **carried}
            )
        return super().with_paths(paths=paths, **kwargs)


class AdminLinkSettings(MQTTClient):
    enabled: bool = False
    name: str = CoreNodeNames.admin
    max_timeout_seconds: float = 60 * 60 * 24

class ScadaSettings(ScadaPathsSettings):
    """Settings for the GridWorks scada."""
    #logging related (temporary)
    pico_cycler_state_logging: bool = False
    unknown_channel_logging: bool = False
    power_meter_logging_level: int = logging.WARNING
    contract_rep_logging_level: int = logging.INFO
    paho_logging: bool = False
    local_mqtt: MQTTClient = MQTTClient(tls=TLSInfo(use_tls=False))
    gridworks_mqtt: MQTTClient = MQTTClient(tls=TLSInfo(use_tls=False))
    clock_source: ClockSource = ClockSource.Wall
    seconds_per_report: int = 300
    seconds_per_snapshot: int = 30
    async_power_reporting_threshold: float = 0.02
    power_meter_lost_after_s: float = POWER_METER_LOST_AFTER_S
    persister: PersisterSettings = PersisterSettings()
    admin: AdminLinkSettings = AdminLinkSettings(tls=TLSInfo(use_tls=False))
    # site facts, here until the TaValidator owns them
    latitude: float = 45.6573
    longitude: float = -68.7098
    # ⏳ Destined for operational-params, not the layout. A heat call is sensed
    # either by opto-coupler (Nolan: BinaryState, DigitalZeroIsActive) or by
    # metering the call wire (House0: PowerW, GreaterThanThreshold). WHICH of
    # the two a circuit uses is a wiring fact the layout owns —
    # ⏳ Destined for the layout as a component + device-type record, not for a
    # bare enum here. The layout is the fleet's record of what is installed at
    # each house, so heat-pump type is tracked there whether or not control
    # code branches on it. Target: an hp-odu component pointing at an
    # hp.device.type.gt record, and an hp-ctrl-box component pointing at
    # hp.control.box.device.type.gt (both words exist in sema; the Nolan layout
    # today has neither, and carries an hp-idu node that should be
    # hp-ctrl-box). Nothing reads it today.
    airtable_pat: str = "bogus_pat"
    model_config = SettingsConfigDict(env_prefix="SCADA_", extra="ignore")
