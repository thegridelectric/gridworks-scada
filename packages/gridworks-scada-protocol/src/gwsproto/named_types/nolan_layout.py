from typing import List, Literal

from pydantic import BaseModel, ConfigDict

from gwsproto.named_types.ads111x_based_device_type_gt import Ads111xBasedDeviceTypeGt
from gwsproto.named_types.electric_meter_device_type_gt import ElectricMeterDeviceTypeGt
from gwsproto.named_types.gw1_scada_device_type_gt import Gw1ScadaDeviceTypeGt
from gwsproto.named_types.data_channel_gt import DataChannelGt
from gwsproto.named_types.g_node_gt import GNodeGt
from gwsproto.named_types.derived_channel_gt import DerivedChannelGt
from gwsproto.named_types.electric_meter_component_gt import ElectricMeterComponentGt
from gwsproto.named_types.gw108_gpio_relay_component_gt import Gw108GpioRelayComponentGt
from gwsproto.named_types.gw108_gpio_sensor_component_gt import Gw108GpioSensorComponentGt
from gwsproto.named_types.i2c_multichannel_dt_relay_component_gt import (
    I2cMultichannelDtRelayComponentGt,
)
from gwsproto.named_types.i2c_thermistor_reader_component_gt import (
    I2cThermistorReaderComponentGt,
)
from gwsproto.named_types.pico_btu_meter_component_gt import PicoBtuMeterComponentGt
from gwsproto.named_types.pico_tank_module_component_gt import PicoTankModuleComponentGt
from gwsproto.named_types.sim_pico_tank_module_component_gt import (
    SimPicoTankModuleComponentGt,
)
from gwsproto.named_types.spaceheat_node_gt import SpaceheatNodeGt
from gwsproto.named_types.web_server_component_gt import WebServerComponentGt

# The component types a Nolan (gw108) layout may contain (mirrors the sema draft oneOf).
NolanComponent = (
    ElectricMeterComponentGt
    | Gw108GpioSensorComponentGt
    | Gw108GpioRelayComponentGt
    | I2cMultichannelDtRelayComponentGt
    | I2cThermistorReaderComponentGt
    | PicoBtuMeterComponentGt
    | PicoTankModuleComponentGt
    | SimPicoTankModuleComponentGt
    | WebServerComponentGt
)

# The specialized device-type records a Nolan layout may carry (mirrors the sema oneOf).
NolanDeviceType = (
    Ads111xBasedDeviceTypeGt
    | ElectricMeterDeviceTypeGt
    | Gw1ScadaDeviceTypeGt
)


class NolanLayout(BaseModel):
    """
    Sema draft: https://schemas.electricity.works/draft/types/gw.nolan.layout/000

    A complete, self-contained configuration + topology snapshot for a Nolan (gw108)
    hydronic space-heating system: identity (GNodes), topology (ShNodes), telemetry
    (DataChannels + DerivedChannels), hardware (Components), per-family device-type
    records (DeviceTypes), and the Hydronic config block. A deployable artifact —
    everything SCADA needs is present, no external registry lookup.

    HAND-COPIED from the sema draft; this is a scada-embedded starting point until the
    sema snapshot runs in scada. **Axioms are NOT yet implemented** — the full set is
    listed (commented) at the bottom and stated in the sema draft yaml. Composes names
    from `hydronic_spaceheat` + `nolan`; required/optional is owned by this layout type
    (e.g. `-gw-temp` REQUIRED for nolan).
    """

    GNodes: List[GNodeGt]
    ShNodes: List[SpaceheatNodeGt]
    DataChannels: List[DataChannelGt]
    DerivedChannels: List[DerivedChannelGt]
    Components: List[NolanComponent]
    DeviceTypes: List[NolanDeviceType]
    Hydronic: dict
    TypeName: Literal["gw.nolan.layout"] = "gw.nolan.layout"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(extra="allow")

    # ------------------------------------------------------------------------
    # AXIOMS — TODO: implement (full statements in the sema draft
    # gw.nolan.layout/000.yaml). Commented out per the scaffold plan; the layout
    # is the authority on required-vs-optional channels + ShNodes.
    # ------------------------------------------------------------------------
    #  1. NolanGNodeSet
    #  2. GlobalIdUniqueness
    #  3. DeviceTypeMembership
    #  4. ComponentConfigListExistence
    #  5. HydronicStructure
    #  6. ShNodeNameUniqueness
    #  7. CoreShNodesExistenceAndActorClass
    #  8. HydronicShNodesExistenceAndActorClass
    #  9. NolanNodesExistenceAndActorClass
    # 10. HandleTopologyRequirements
    # 11. ActorHierarchyClosure
    # 12. ZoneShNodeStructure
    # 13. TankShNodeStructure
    # 14. ComponentReferenceIntegrity
    # 15. CoreChannelExistence
    # 16. HydronicChannelExistence
    # 17. NolanChannelExistence
    # 18. TankChannelStructure
    # 19. ZoneChannelStructure
    # 20. ChannelBindingIntegrity
    # 21. ComponentDataChannelBijection
    # 22. ChannelCaptureConsistency
    # 23. RelayBoardConfigBijection
    # 24. PowerMeteringNodeChannelConsistency
    # 25. AssetElectricPowerSemantics
    # 26. PowerMeteringChannelSemantics
    # 27. PipeTemperatureChannelSemantics
    # 28. TankTemperatureChannelSemantics
    # 29. PipeFlowChannelSemantics
    # 30. EnergyChannelSemantics
    # 31. VdcRelaySemantics
    # 32. ElementRelaySemantics
    # 33. ZoneFailsafeRelaySemantics
    # 34. ZoneOpsRelaySemantics
    # 35. ZoneRoomTempChannelSemantics
    # 36. ZoneSetpointChannelSemantics
    # 37. ZoneFloorTempChannelSemantics
    # 38. HeatCallChannelSemantics
    # 39. MakeModelCacIdConsistency (draft/deferred)
