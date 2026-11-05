import re
import logging

from pydantic import BaseModel, PositiveInt, field_validator
from pydantic_settings import SettingsConfigDict

from gwproactor.config import MQTTClient

from actors.config import ScadaPathsSettings
from actors.ltn.market import MARKET_SLOT_S
from clock import ClockSource
from weather_source import WeatherSourceKind


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

class LtnSettings(ScadaPathsSettings):
    scada_mqtt: MQTTClient = MQTTClient()
    c_to_f: bool = True
    save_events: bool = False
    dashboard: DashboardSettings = DashboardSettings()
    timezone_str: str = "America/New_York"
    fuel_substitution: bool = False
    fuel_sub_usd_per_mwh: int = 490 # hack until we account for COP etc
    contract_rep_logging_level: int = logging.INFO
    flo_logging_level: int = logging.INFO
    flo_horizon_hours: int = 48
    # How many seconds before a market slot starts the LTN measures the
    # store, asks the FLO and bids for that slot. Less than one slot, so
    # each slot gets exactly one request.
    bid_lead_s: PositiveInt = 180
    # Count no buffer energy when true.
    keep_buffer_full: bool = False
    clock_source: ClockSource = ClockSource.Wall
    weather_source: WeatherSourceKind = WeatherSourceKind.Gwwf
    weather_api_url: str = "https://forecast.electricity.works/hw1-isone-weather"
    weather_pull_timeout_s: float = 20

    model_config = SettingsConfigDict(env_prefix="LTN_", extra="ignore")

    @field_validator("bid_lead_s")
    @classmethod
    def bid_lead_is_inside_one_slot(cls, v: int) -> int:
        if v >= MARKET_SLOT_S:
            raise ValueError(
                f"bid_lead_s must be less than the market slot ({MARKET_SLOT_S} s), got {v}"
            )
        return v


