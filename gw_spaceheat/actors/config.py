import logging
from pathlib import Path

from pydantic import model_validator
from gwproactor import AppSettings
from gwproactor.config.mqtt import TLSInfo
from pydantic import BaseModel

from gwsproto.data_classes.house_0_names import H0N
from gwproactor.config import MQTTClient
from pydantic_settings import SettingsConfigDict
from gwsproto.enums import HpModel

# gridworks-scada/tests/config/nolan-layout.json
DEFAULT_TEST_LAYOUT = (
    Path(__file__).resolve()
    .parents[2]   # adjust depth as needed
    / "tests"
    / "config"
    / "nolan-layout.json"
)


DEFAULT_MAX_EVENT_BYTES: int = 500 * 1024 * 1024

class PersisterSettings(BaseModel):
    max_bytes: int = DEFAULT_MAX_EVENT_BYTES


class AdminLinkSettings(MQTTClient):
    enabled: bool = False
    name: str = H0N.admin
    max_timeout_seconds: float = 60 * 60 * 24

class ScadaSettings(AppSettings):
    """Settings for the GridWorks scada."""
    #logging related (temporary)
    pico_cycler_state_logging: bool = False
    power_meter_logging_level: int = logging.WARNING
    contract_rep_logging_level: int = logging.INFO
    relay_multiplexer_logging_level: int = logging.INFO
    paho_logging: bool = False
    local_mqtt: MQTTClient = MQTTClient(tls=TLSInfo(use_tls=False))
    gridworks_mqtt: MQTTClient = MQTTClient(tls=TLSInfo(use_tls=False))
    seconds_per_report: int = 300
    seconds_per_snapshot: int = 30
    async_power_reporting_threshold: float = 0.02
    persister: PersisterSettings = PersisterSettings()
    admin: AdminLinkSettings = AdminLinkSettings(tls=TLSInfo(use_tls=False))
    timezone_str: str = "America/New_York"
    # The control/optimization values (modes, curves, knobs, lat/lon) live in
    # the authored gw.house0.operational.params artifact, loaded at startup —
    # empty path means the per-home sibling dir of the hardware layout.
    operational_params_path: str = ""
    hp_max_kw_el: float = 9.66  # TODO: move to layout (nameplate)
    is_simulated: bool = False
    whitewire_threshold_watts: float = 20 # TODO: move to layout
    hp_model: HpModel = HpModel.SamsungFiveTonneHydroKit # TODO: move to layout
    airtable_pat: str = "bogus_pat"
    model_config = SettingsConfigDict(env_prefix="SCADA_", extra="ignore")
