"""Container for data Scada uses in building status and snapshot messages, separated from Scada for clarity,
not necessarily re-use. """

import time
import uuid
from typing import Dict, List, Optional, Union

from actors.config import ScadaSettings
from gwproto.data_classes.data_channel import DataChannel
from gwproto.data_classes.synth_channel import SynthChannel
from gwproto.data_classes.hardware_layout import HardwareLayout
from gwproto.messages import (
    ChannelReadings,
    FsmFullReport,
    MachineStates,
    Report,
    SingleReading,
)

from named_types import Ha1Params, SingleMachineState, SnapshotSpaceheat
class ScadaData:
    reports_to_store: Dict[str, Report]
    recent_machine_states: Dict[str, MachineStates] # key is machine handle
    latest_machine_state: Dict[str, SingleMachineState] # key is the node name
    latest_channel_unix_ms: Dict[str, int]
    latest_channel_values: Dict[str, int]
    recent_channel_values: Dict[str, List]
    recent_channel_unix_ms: Dict[str, List]
    recent_fsm_reports: Dict[str, FsmFullReport]
    settings: ScadaSettings
    layout: HardwareLayout
    ha1_params: Ha1Params

    def __init__(self, settings: ScadaSettings, hardware_layout: HardwareLayout):
        self.reports_to_store: Dict[str:Report] = {}
        self.seconds_by_channel: Dict[str:int] = {}

        self.settings = settings
        self.layout = hardware_layout
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
            HpMaxKwTh=self.settings.hp_max_kw_th,
            MaxEwtF=self.settings.max_ewt_f,
            LoadOverestimationPercent=self.settings.load_overestimation_percent,
            StratBossDist010=0 # REMOVE AT SOME POINT
        )
        self.my_data_channels = self.get_my_data_channels()
        self.my_synth_channels = self.get_my_synth_channels()
        self.my_channels: Union[DataChannel, SynthChannel] = self.my_data_channels + self.my_synth_channels
        self.recent_machine_states = {}
        self.latest_machine_state = {}
        self.latest_channel_values: Dict[str, int] = {  # noqa
            ch.Name: None for ch in self.my_channels
        }
        self.latest_channel_unix_ms: Dict[str, int] = {  # noqa
            ch.Name: None for ch in self.my_channels
        }
        self.recent_channel_values: Dict[str, List] = {
            ch.Name: [] for ch in self.my_channels
        }
        self.recent_channel_unix_ms: Dict[str, List] = {
            ch.Name: [] for ch in self.my_channels
        }
        self.recent_fsm_reports = {}
        self.flush_recent_readings()

    def get_my_data_channels(self) -> List[DataChannel]:
        return list(self.layout.data_channels.values())
    
    def get_my_synth_channels(self) -> List[SynthChannel]:
        return list(self.layout.synth_channels.values())

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
                ChannelId=ch.Id,
                ValueList=self.recent_channel_values[ch.Name],
                ScadaReadTimeUnixMsList=self.recent_channel_unix_ms[ch.Name],
            )
        else:
            return None

    def make_report(self, slot_start_seconds: int) -> Report:
        channel_reading_list = []
        for ch in self.my_channels:
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

    def capture_seconds(self, ch: Union[DataChannel, SynthChannel]) -> int:
        if ch.Name not in self.seconds_by_channel:
            self.seconds_by_channel = {}
            components = [c.gt for c in self.layout.components.values()]
            for c in components:
                for config in c.ConfigList:
                    self.seconds_by_channel[config.ChannelName] = config.CapturePeriodS
            for s in self.my_synth_channels:
                self.seconds_by_channel[s.Name] = s.SyncReportMinutes * 60
        return self.seconds_by_channel[ch.Name]

    def flatlined(self, ch: Union[DataChannel, SynthChannel]) -> bool:
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
