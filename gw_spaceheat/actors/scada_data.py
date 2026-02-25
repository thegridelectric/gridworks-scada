"""Container for data Scada uses in building status and snapshot messages, separated from Scada for clarity,
not necessarily re-use. """

import time
import uuid
from typing import Dict, List, Optional, Union

from actors.config import ScadaSettings
from gwsproto.data_classes.data_channel import DataChannel
from gwsproto.data_classes.house_0_names import H0CN
from gwsproto.named_types import (
    ChannelReadings,
    Report,
    SingleReading,
    SingleMachineState,
)

from gwsproto.named_types import (
    Ha1Params,
    HeatingForecast,
    SnapshotSpaceheat,
)

from gwsproto.data_classes.derived_channel import DerivedChannel
from gwsproto.data_classes.house_0_layout import House0Layout
class ScadaData:

    def __init__(self, settings: ScadaSettings, hardware_layout: House0Layout):
        self.reports_to_store: Dict[str, Report] = {}
        self.seconds_by_channel: Dict[str, int] = {}

        self.settings: ScadaSettings = settings
        self.layout: House0Layout = hardware_layout
        # TODO: move into layout when better UI for it
        self.ha1_params = Ha1Params(
            AlphaTimes10=int(self.settings.alpha * 10),
            BetaTimes100=int(self.settings.beta * 100),
            GammaEx6=int(self.settings.gamma * 1e6),
            IntermediatePowerKw=self.settings.intermediate_power,
            IntermediateRswtF=int(self.settings.intermediate_rswt),
            DdPowerKw=self.settings.dd_power,
            DdRswtF=int(self.settings.dd_rswt),
            DdDeltaTF=int(self.settings.dd_delta_t),
            HpMaxKwEl=self.settings.hp_max_kw_el,
            MaxEwtF=self.settings.max_ewt_f,
            LoadOverestimationPercent=self.settings.load_overestimation_percent,
            CopIntercept=self.settings.cop_intercept,
            CopOatCoeff=self.settings.cop_oat_coeff,
            CopLwtCoeff=self.settings.cop_lwt_coeff,
            CopMin=self.settings.cop_min,
            CopMinOatF=self.settings.cop_min_oat_f,
        )
        self.my_data_channels = self.get_my_data_channels()
        self.my_derived_channels = self.get_my_derived_channels()
        self.my_channels: list[Union[DataChannel, DerivedChannel]] = self.my_data_channels + self.my_derived_channels
        self.recent_machine_states = {}
        self.latest_machine_state: dict[str, SingleMachineState] = {} # latest state by node name
        self.latest_channel_values: Dict[str, int | None] = {
            ch.Name: None for ch in self.my_channels
        }
        self.latest_channel_unix_ms: Dict[str, int | None] = {
            ch.Name: None for ch in self.my_channels
        }
        self.latest_temperatures_f: Dict[str, float] = {}
        self.buffer_temps_available: bool = False # change to buffer_available

        self.latest_channel_values[H0CN.usable_energy] = 0
        self.latest_channel_unix_ms[H0CN.usable_energy] = int(time.time() * 1000)
        self.recent_channel_values: Dict[str, List] = {
            ch.Name: [] for ch in self.my_channels
        }
        self.recent_channel_unix_ms: Dict[str, List] = {
            ch.Name: [] for ch in self.my_channels
        }
        self.latest_power_w: Optional[int] = None
        self.heating_forecast: HeatingForecast | None = None
        self.recent_fsm_reports = {}
        self.flush_recent_readings()

    def get_my_data_channels(self) -> List[DataChannel]:
        return list(self.layout.data_channels.values())
    
    def get_my_derived_channels(self) -> List[DerivedChannel]:
        return list(self.layout.derived_channels.values())

    def channel_has_value(self, channel: str) -> bool:
        return (
            channel in self.latest_channel_values
            and self.latest_channel_values[channel] is not None
        )

    def flush_channel_from_latest(self, channel_name: str) -> None:
        """
        A data channel has flatlined; set its dict value to None
        """
        if channel_name in self.latest_channel_values and self.latest_channel_values[channel_name] is not None:
            print(f"Channel {channel_name} flatlined - removing from snapshots!")
        self.latest_channel_values[channel_name] = None
        self.latest_channel_unix_ms[channel_name] = None

    def flush_recent_readings(self):
        self.recent_channel_values = {ch.Name: [] for ch in self.my_channels}
        self.recent_channel_unix_ms = {ch.Name: [] for ch in self.my_channels}
        self.recent_fsm_reports = {}
        self.recent_machine_states = {}

    def make_channel_readings(self, ch: DataChannel) -> Optional[ChannelReadings]:
        if ch in self.my_channels:
            if len(self.recent_channel_values[ch.Name]) == 0:
                return None
            return ChannelReadings(
                ChannelName=ch.Name,
                ValueList=self.recent_channel_values[ch.Name],
                ScadaReadTimeUnixMsList=self.recent_channel_unix_ms[ch.Name],
            )
        else:
            return None

    @property
    def my_reported_channels(self) -> list[Union[DataChannel, DerivedChannel]]:
        """
        Channels that should be included in reports.
        """
        return [
            ch for ch in self.my_channels
            if ch.Name not in self.layout.unreported_channels
        ]

    def make_report(self, slot_start_seconds: int) -> Report:
        channel_reading_list = []
        for ch in self.my_reported_channels:
            channel_readings = self.make_channel_readings(ch)
            if channel_readings:
                channel_reading_list.append(channel_readings)

        return Report(
            FromGNodeAlias=self.layout.scada_g_node_alias,
            FromGNodeInstanceId=self.layout.scada_g_node_id,
            AboutGNodeAlias=self.layout.terminal_asset_g_node_alias,
            SlotStartUnixS=slot_start_seconds,
            SlotDurationS=self.settings.seconds_per_report,
            ChannelReadingList=channel_reading_list,
            StateList=list(self.recent_machine_states.values()),
            FsmReportList=list(self.recent_fsm_reports.values()),
            MessageCreatedMs=int(time.time() * 1000),
            Id=str(uuid.uuid4()),
        )

    def capture_seconds(self, ch: Union[DataChannel, DerivedChannel]) -> int:
        if ch.Name not in self.seconds_by_channel:
            self.seconds_by_channel = {}
            components = [c.gt for c in self.layout.components.values()]
            for c in components:
                for config in c.ConfigList:
                    self.seconds_by_channel[config.ChannelName] = config.CapturePeriodS
            for s in self.my_derived_channels:
                self.seconds_by_channel[s.Name] = 60  # TODO: fix
        return self.seconds_by_channel[ch.Name]

    def flatlined(self, ch: Union[DataChannel, DerivedChannel]) -> bool:
        if self.latest_channel_unix_ms[ch.Name] is None:
            return True
        # nyquist
        nyquist = 2.1  # https://en.wikipedia.org/wiki/Nyquist_frequency
        if (
            time.time() - (self.latest_channel_unix_ms[ch.Name] / 1000)
            > self.capture_seconds(ch) * nyquist
        ):
            return True
        return False

    def make_snapshot(self) -> SnapshotSpaceheat:
        latest_reading_list = []

        for ch in self.my_channels:
            if not self.flatlined(ch):
                latest_reading_list.append(
                    SingleReading(
                        ChannelName=ch.Name,
                        Value=self.latest_channel_values[ch.Name],
                        ScadaReadTimeUnixMs=self.latest_channel_unix_ms[ch.Name],
                    )
                )
        return SnapshotSpaceheat(
            FromGNodeAlias=self.layout.scada_g_node_alias,
            FromGNodeInstanceId=self.layout.scada_g_node_id,
            SnapshotTimeUnixMs=int(time.time() * 1000),
            LatestReadingList=latest_reading_list,
            LatestStateList=list(self.latest_machine_state.values()),
        )
