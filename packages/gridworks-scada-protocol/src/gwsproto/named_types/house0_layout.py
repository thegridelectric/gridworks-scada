from typing import List, Literal, Optional

from pydantic import BaseModel

from gwsproto.named_types.ads111x_based_component_gt import Ads111xBasedComponentGt
from gwsproto.named_types.component_attribute_class_gt import ComponentAttributeClassGt
from gwsproto.named_types.data_channel_gt import DataChannelGt
from gwsproto.named_types.derived_channel_gt import DerivedChannelGt
from gwsproto.named_types.dfr_component_gt import DfrComponentGt
from gwsproto.named_types.electric_meter_component_gt import ElectricMeterComponentGt
from gwsproto.named_types.g_node_gt import GNodeGt
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


class House0Layout(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/gw.house0.layout/000

    A complete, self-contained config + topology snapshot for a House0-fleet
    hydronic system (beech, elm, oak, fir, maple). Sema is the source of truth;
    this gwsproto class is hand-ported to match, then tested via the layout
    round-trip script.

    Shape laid out, content built up bit by bit: only TypeName + Version are
    required at v000; the collections are optional while they are populated and
    the structural axioms are added. DeviceTypes uses the ComponentAttributeClassGt
    base as a stand-in until the specialized <family>.device.type.gt records are
    gwsproto classes (carried debt, mirrors the Nolan scaffold).
    """

    GNodes: Optional[List[GNodeGt]] = None
    ShNodes: Optional[List[SpaceheatNodeGt]] = None
    DataChannels: Optional[List[DataChannelGt]] = None
    DerivedChannels: Optional[List[DerivedChannelGt]] = None
    Components: Optional[List[House0Component]] = None
    DeviceTypes: Optional[List[ComponentAttributeClassGt]] = None
    Hydronic: Optional[dict] = None
    TypeName: Literal["gw.house0.layout"] = "gw.house0.layout"
    Version: Literal["000"] = "000"
