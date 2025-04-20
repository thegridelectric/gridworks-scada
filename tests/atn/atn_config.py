import re
import logging
from pydantic import BaseModel
from pydantic import model_validator
from enums import HpModel
from gwproactor import ProactorSettings
from gwproactor.config import MQTTClient
from pydantic_settings import SettingsConfigDict

DEFAULT_NAME = "atn"

class HackHpSettings(BaseModel):
    ops_genie_api_key: str = ""
    gridworks_team_id: str = ""
    moscone_team_id: str = ""

class DashboardSettings(BaseModel):
    print_report: bool = False
    print_snap: bool = False
    print_gui: bool = True
    print_hack_hp: bool = False
    print_thermostat_history: bool = False
    raise_dashboard_exceptions: bool = False
    hack_hp: HackHpSettings = HackHpSettings()

    @classmethod
    def thermostat_names(cls, channel_names: list[str]) -> list[str]:
        thermostat_channel_name_pattern = re.compile(
            r"^zone(?P<zone_number>\d)-(?P<human_name>.*)-(temp|set|state)$"
        )
        thermostat_human_names = []
        for channel_name in channel_names:
            if match := thermostat_channel_name_pattern.match(channel_name):
                if (human_name := match.group("human_name")) not in thermostat_human_names:
                    thermostat_human_names.append(human_name)
        return thermostat_human_names

class AtnSettings(ProactorSettings):
    scada_mqtt: MQTTClient = MQTTClient()
    c_to_f: bool = True
    save_events: bool = False
    dashboard: DashboardSettings = DashboardSettings()
    timezone_str: str = "America/New_York"
    latitude: float = 45.6573 
    longitude: float = -68.7098
    is_simulated: bool = False
    fuel_substitution: bool = True
    fuel_sub_usd_per_mwh: int = 250 # hack until we account for COP etc
    hp_model: HpModel = HpModel.SamsungFiveTonneHydroKit # TODO: move to layout
    model_config = SettingsConfigDict(env_prefix="ATN_", extra="ignore")
    contract_rep_logging_level: int = logging.INFO
    flo_logging_level: int = logging.INFO
    monitor_only: bool = False
    
    @model_validator(mode="before")
    @classmethod
    def pre_root_validator(cls, values: dict) -> dict:
        return ProactorSettings.update_paths_name(values, DEFAULT_NAME)

