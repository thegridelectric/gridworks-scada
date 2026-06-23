from typing import Literal

from pydantic import BaseModel, model_validator
from typing_extensions import Self

from gwsproto.named_types.ads111x_based_component_gt import Ads111xBasedComponentGt
from gwsproto.named_types.ads111x_based_device_type_gt import Ads111xBasedDeviceTypeGt
from gwsproto.named_types.electric_meter_device_type_gt import ElectricMeterDeviceTypeGt
from gwsproto.named_types.scada_device_type_gt import ScadaDeviceTypeGt
from gwsproto.named_types.data_channel_gt import DataChannelGt
from gwsproto.named_types.derived_channel_gt import DerivedChannelGt
from gwsproto.named_types.dfr_component_gt import DfrComponentGt
from gwsproto.named_types.electric_meter_component_gt import ElectricMeterComponentGt
from gwsproto.named_types.g_node_gt import GNodeGt
from gwsproto.named_types.house0_hydronic import House0Hydronic
from gwsproto.named_types.hubitat_component_gt import HubitatComponentGt
from gwsproto.named_types.hubitat_poller_component_gt import HubitatPollerComponentGt
from gwsproto.named_types.i2c_multichannel_dt_relay_component_gt import (
    I2cMultichannelDtRelayComponentGt,
)
from gwsproto.named_types.pico_btu_meter_component_gt import PicoBtuMeterComponentGt
from gwsproto.named_types.pico_flow_module_component_gt import PicoFlowModuleComponentGt
from gwsproto.named_types.pico_tank_module_component_gt import PicoTankModuleComponentGt
from gwsproto.named_types.sim_pico_tank_module_component_gt import (
    SimPicoTankModuleComponentGt,
)
from gwsproto.named_types.spaceheat_node_gt import SpaceheatNodeGt
from gwsproto.named_types.web_server_component_gt import WebServerComponentGt

# The component types a House0 (fleet) layout may contain (mirrors the sema oneOf).
House0Component = (
    ElectricMeterComponentGt
    | Ads111xBasedComponentGt
    | I2cMultichannelDtRelayComponentGt
    | DfrComponentGt
    | PicoBtuMeterComponentGt
    | PicoFlowModuleComponentGt
    | PicoTankModuleComponentGt
    | SimPicoTankModuleComponentGt
    | HubitatComponentGt
    | HubitatPollerComponentGt
    | WebServerComponentGt
)

# The specialized device-type records a House0 layout may carry (mirrors the sema oneOf).
House0DeviceType = (
    Ads111xBasedDeviceTypeGt
    | ElectricMeterDeviceTypeGt
    | ScadaDeviceTypeGt
)


class House0Layout(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/gw.house0.layout/000
    """

    GNodes: list[GNodeGt]
    ShNodes: list[SpaceheatNodeGt]
    DataChannels: list[DataChannelGt]
    DerivedChannels: list[DerivedChannelGt]
    Components: list[House0Component]
    DeviceTypes: list[House0DeviceType]
    Hydronic: House0Hydronic
    TypeName: Literal["gw.house0.layout"] = "gw.house0.layout"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: GlobalIdUniqueness
        ShNode.ShNodeId, Component.ComponentId, DataChannel.Id, DerivedChannel.Id
        and GNode.GNodeId SHALL each be globally unique; no id value SHALL appear
        in more than one of these sets.
        """
        ids: list[str] = []
        ids += [n.ShNodeId for n in (self.ShNodes or [])]
        ids += [c.ComponentId for c in (self.Components or [])]
        ids += [d.Id for d in (self.DataChannels or [])]
        ids += [d.Id for d in (self.DerivedChannels or [])]
        ids += [g.GNodeId for g in (self.GNodes or [])]
        seen: set[str] = set()
        dupes: set[str] = set()
        for i in ids:
            if i in seen:
                dupes.add(i)
            seen.add(i)
        if dupes:
            raise ValueError(
                f"Axiom 1 (GlobalIdUniqueness) failed: duplicate ids {sorted(dupes)}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: EssentialNodesExistence
        ShNodes SHALL include the primary-scada (s), ltn, leaf-ally (la),
        local-control (lc) and derived-generator nodes.
        """
        if not self.ShNodes:
            return self
        required = {"s", "ltn", "la", "lc", "derived-generator"}
        names = {n.Name for n in (self.ShNodes or [])}
        missing = sorted(required - names)
        if missing:
            raise ValueError(
                f"Axiom 2 (EssentialNodesExistence) failed: missing essential nodes {missing}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: ZoneWhitewirePwrChannel
        For each zone at 1-based index i in Hydronic.Zones, a channel named
        "zone{i}-{Zone.Name}-whitewire-pwr" (lowercased) SHALL exist in the union
        of DataChannels and DerivedChannels.
        """
        if self.Hydronic is None:
            return self
        channels = {d.Name for d in (self.DataChannels or [])}
        channels |= {d.Name for d in (self.DerivedChannels or [])}
        for i, zone in enumerate(self.Hydronic.Zones or [], start=1):
            name = f"zone{i}-{zone.Name}".lower() + "-whitewire-pwr"
            if name not in channels:
                raise ValueError(
                    f"Axiom 3 (ZoneWhitewirePwrChannel) failed: missing channel '{name}'."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: PrimaryFlowSourceChannelAgreement
        The "primary-flow" channel SHALL agree with Hydronic.PrimaryFlowSource. If
        PrimaryFlowSource is "Measured", a DataChannel named "primary-flow" SHALL exist
        and no DerivedChannel named "primary-flow" SHALL exist. If PrimaryFlowSource is
        "DerivedSiegSum", a DerivedChannel named "primary-flow" with Strategy "sum" SHALL
        exist and no DataChannel named "primary-flow" SHALL exist.
        """
        if self.Hydronic is None:
            return self
        source = self.Hydronic.PrimaryFlowSource
        has_data = any(d.Name == "primary-flow" for d in (self.DataChannels or []))
        derived = [d for d in (self.DerivedChannels or []) if d.Name == "primary-flow"]
        if source == "Measured":
            if not has_data:
                raise ValueError(
                    "Axiom 4 (PrimaryFlowSourceChannelAgreement) failed: Measured requires a "
                    "'primary-flow' DataChannel."
                )
            if derived:
                raise ValueError(
                    "Axiom 4 (PrimaryFlowSourceChannelAgreement) failed: Measured forbids a "
                    "'primary-flow' DerivedChannel."
                )
        elif source == "DerivedSiegSum":
            if not any(d.Strategy == "sum" for d in derived):
                raise ValueError(
                    "Axiom 4 (PrimaryFlowSourceChannelAgreement) failed: DerivedSiegSum requires "
                    "a 'primary-flow' DerivedChannel with Strategy 'sum'."
                )
            if has_data:
                raise ValueError(
                    "Axiom 4 (PrimaryFlowSourceChannelAgreement) failed: DerivedSiegSum forbids a "
                    "'primary-flow' DataChannel."
                )
        return self
