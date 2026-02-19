import json
from pathlib import Path

from typing import Union
from gwsproto.data_classes.house_0_names import H0CN
from gwsproto.named_types import LayoutLite
from gwsproto.data_classes.layout_lite_dc import LayoutLiteDc
from gwsproto.named_types import (
    DataChannelGt, DerivedChannelGt, 
    Report, SnapshotSpaceheat
)


class LtnData:

    def __init__(self):
        self.latest_channel_values: dict[str, int] = {}
        self.latest_temperatures_f: dict[str, float] = {}
        self.layout_lite:  LayoutLiteDc | None = None
        self.latest_snapshot: SnapshotSpaceheat | None = None
        self.latest_report: Report | None = None
        self.latest_power_w: int | None = None
        self.tank_temps_available: bool = False

    def my_data_channels(self) -> list[DataChannelGt]:
        if self.layout_lite is None:
            return []
        else:
            return self.layout_lite.gt.DataChannels

    def my_derived_channels(self) -> list[DerivedChannelGt]:
        if self.layout_lite is None:
            return []
        else:
            return self.layout_lite.gt.DerivedChannels

    def my_channels(self) -> list[Union[DataChannelGt, DerivedChannelGt]]:
        return self.my_data_channels() + self.my_derived_channels()

    @property
    def h0cn(self) -> H0CN | None:
        if self.layout_lite is None:
            return None
        else:
            return self.layout_lite.h0cn

    @property
    def tank_temp_channel_names(self) -> list[str]:
        if self.layout_lite is None:
            return []
        return self.layout_lite.tank_temp_channel_names

    @property
    def store_tank_temp_channel_names(self) -> list[str]:
        if self.layout_lite is None:
            return []
        return self.layout_lite.store_tank_temp_channel_names

    def load_simulated_layout_lite(self) -> None:
        """
        Load a LayoutLite fixture for simulated Ltn operation.
        """
        path = Path(__file__).parents[2] / "tests" / "config.layout-lite.json"

        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        layout_gt = LayoutLite(**payload)
        self.layout_lite = self.load_layout_lite(layout_gt)

    def load_layout_lite(self, layout_gt: LayoutLite) -> None:
        self.layout_lite = LayoutLiteDc(layout_gt)

    @property
    def total_store_tanks(self) -> int:
        if self.layout_lite is None:
            return 3
        return self.layout_lite.total_store_tanks