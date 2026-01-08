import time

from typing import Optional

import rich
from gwproactor.logger import LoggerOrAdapter

from gwsproto.named_types import SnapshotSpaceheat, PowerWatts


from actors.atn.dashboard.misc import UpdateSources
from actors.atn.atn_config import DashboardSettings
from gwsproto.data_classes.hardware_layout import ChannelRegistry
from actors.atn.dashboard.channels.containers import Channels
from actors.atn.dashboard.display.displays import Displays
from actors.atn.dashboard.hackhp import HackHp

class Dashboard:

    def __init__(self,
        settings: DashboardSettings,
        atn_g_node_alias: str,
        data_channels: ChannelRegistry,
        logger: LoggerOrAdapter,
        thermostat_names: list[str] = [],
    ):
        self.settings = settings
        self.short_name = atn_g_node_alias.split(".")[-1]

        self.logger = logger

        self.latest_snapshot: SnapshotSpaceheat | None = None

        self.hack_hp = HackHp(
            short_name=self.short_name,
            settings=self.settings.hack_hp,
            logger=self.logger,
            raise_dashboard_exceptions=self.settings.raise_dashboard_exceptions,
        )
        self.channels = Channels(
            channels=data_channels,
            thermostat_names=thermostat_names
        )
        self.displays = Displays(
            self.settings,
            self.short_name,
            self.channels,
            self.hack_hp.state_q
        )

    def update(
            self,
            *,
            fast_path_power_w: Optional[float],
            report_time_s: int,
    ):
        if self.latest_snapshot is None:
            return
        try:
            self.channels.read_snapshot(self.latest_snapshot)
            self.hack_hp.update_pwr(
                fastpath_pwr_w=fast_path_power_w,
                channels=self.channels,
                report_time_s=report_time_s,
            )
            rich.print(
                self.displays.update(
                    UpdateSources.Power if fast_path_power_w is not None else UpdateSources.Snapshot,
                    report_time_s=report_time_s,
                )
            )
        except Exception as e:
            self.logger.error("ERROR in refresh_gui")
            self.logger.exception(e)
            if self.settings.raise_dashboard_exceptions:
                raise

    def process_snapshot(self, snapshot: SnapshotSpaceheat):
        # rich.print("++process_snapshot")
        self.latest_snapshot = snapshot
        self.update(fast_path_power_w=None, report_time_s=int(snapshot.SnapshotTimeUnixMs / 1000))
        # rich.print("--process_snapshot")

    def process_power(self, power: PowerWatts) -> None:
        if self.latest_snapshot is None:
            return
        self.update(fast_path_power_w=power.Watts, report_time_s=int(time.time()))
        # rich.print("--process_power")
