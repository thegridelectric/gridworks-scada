from functools import cached_property

from gwsproto.data_classes.sh_node import ShNode
from gwsproto.data_classes.data_channel import DataChannel
from gwsproto.data_classes.derived_channel import DerivedChannel
from gwsproto.data_classes.house_0_names import H0CN
from gwsproto.data_classes.hardware_layout import ChannelRegistry
from gwsproto.named_types import LayoutLite


class LayoutLiteDc(LayoutLite):
    def __init__(self, layout_lite: LayoutLite):
        self._gt = layout_lite


    @property
    def gt(self) -> LayoutLite:
        return self._gt

    @cached_property
    def h0cn(self) -> H0CN:
        return H0CN(
            total_store_tanks=self._gt.TotalStoreTanks,
            zone_list=self._gt.ZoneList
        )

    @property
    def total_store_tanks(self) -> int:
        return self._gt.TotalStoreTanks

    @cached_property
    def sh_node_by_name(self) -> dict[str, ShNode]:
        return {
            n.Name: ShNode(**n.model_dump())
            for n in self._gt.ShNodes
        }

    @cached_property
    def data_channels(self) -> dict[str, DataChannel]:
        channels: dict[str, DataChannel] = {}
        nodes = self.sh_node_by_name

        for dc_gt in self._gt.DataChannels:
            # Safe to index directly: Axiom 1 guarantees node existence
            about_node = nodes[dc_gt.AboutNodeName]
            captured_by_node = nodes[dc_gt.CapturedByNodeName]

            dc = DataChannel(
                **dc_gt.model_dump(),
                about_node=about_node,
                captured_by_node=captured_by_node,
            )

            channels[dc.Name] = dc

        return channels

    @cached_property
    def derived_channels(self) -> dict[str, DerivedChannel]:
        channels: dict[str, DerivedChannel] = {}
        nodes = self.sh_node_by_name

        for dc_gt in self._gt.DerivedChannels:
            # Safe to index directly: Axiom 4 guarantees node existence
            created_by_node = nodes[dc_gt.CreatedByNodeName]

            dc = DerivedChannel(
                **dc_gt.model_dump(),
                created_by_node=created_by_node,
            )

            channels[dc.Name] = dc

        return channels

    @cached_property
    def channel_registry(self) -> ChannelRegistry:
        return ChannelRegistry(
            data_channels=self.data_channels,
            derived_channels=self.derived_channels,
        )

    @property
    def tank_temp_channel_names(self) -> list[str]:
        names: list[str] = []

        # buffer effective depths
        names.extend(self.h0cn.buffer.effective)

        # store tanks
        for tank_idx in sorted(self.h0cn.tank):
            tank = self.h0cn.tank[tank_idx]
            names.extend([tank.depth1, tank.depth2, tank.depth3])

        return names

    @cached_property
    def store_tank_temp_channel_names(self) -> list[str]:
        """
        Temperature channels for store tanks only (excludes buffer).
        """
        names: list[str] = []

        # store tanks are indexed starting at 1
        for tank_idx in range(1, self._gt.TotalStoreTanks + 1):
            tank = self.h0cn.tank[tank_idx]
            names.extend([tank.depth1, tank.depth2, tank.depth3])

        return sorted(names)