import logging
from pathlib import Path

from pydantic import model_validator
from gwproactor import AppSettings
from gwproactor.config.mqtt import TLSInfo
from pydantic import BaseModel

from gwsproto.data_classes.house_0_names import H0N
from gwproactor.config import MQTTClient
from pydantic_settings import SettingsConfigDict
from gwsproto.enums import HpModel, SystemMode, SeasonalStorageMode

# gridworks-scada/tests/config/hardware-layout.json
DEFAULT_TEST_LAYOUT = (
    Path(__file__).resolve()
    .parents[2]   # adjust depth as needed
    / "tests"
    / "config"
    / "hardware-layout.json"
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
    gridworks_mqtt: MQTTClient = MQTTClient()
    seconds_per_report: int = 300
    seconds_per_snapshot: int = 30
    async_power_reporting_threshold: float = 0.02
    persister: PersisterSettings = PersisterSettings()
    admin: AdminLinkSettings = AdminLinkSettings()
    timezone_str: str = "America/New_York"
    latitude: float = 45.6573 
    longitude: float = -68.7098
    alpha: float = 5.5
    beta: float = -0.1
    gamma: float = 0
    hp_max_kw_th: float = 14
    intermediate_power: float = 1.5
    intermediate_rswt: float = 100
    dd_power: float = 5.5
    dd_rswt: float = 150
    dd_delta_t: float = 20
    is_simulated: bool = False
    max_ewt_f: int = 170
    load_overestimation_percent: int = 0
    oil_boiler_backup: bool = True
    system_mode: SystemMode = SystemMode.Heating
    seasonal_storage_mode: SeasonalStorageMode = SeasonalStorageMode.AllTanks
    whitewire_threshold_watts: float = 20 # TODO: move to layout
    hp_model: HpModel = HpModel.SamsungFiveTonneHydroKit # TODO: move to layout
    model_config = SettingsConfigDict(env_prefix="SCADA_", extra="ignore")
