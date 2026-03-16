from typing import Sequence
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HNN
from gwsproto.names.hydronic_spaceheat.helpers import Tanks
from gwsproto.names.nolan.helpers import NolanZoneNodeNames
from gwsproto.names.core.node_names import CoreNodeNames as CNN

class NolanNodeNames:
    primary_scada = CNN.primary_scada
    secondary_scada = CNN.secondary_scada
    asset_power_meter = CNN.asset_power_meter
    ltn = CNN.ltn
    leaf_ally = CNN.leaf_ally
    local_control = CNN.local_control
    admin = CNN.admin
    auto = CNN.auto
    derived_generator = CNN.derived_generator

    local_control_normal = HNN.local_control_normal
    local_control_backup = HNN.local_control_backup
    local_control_scada_blind = HNN.local_control_scada_blind

    # transactive asset nodes
    heat_pump = HNN.heat_pump
    buffer_top_elt = HNN.buffer_top_elt
    buffer_bottom_elt = HNN.buffer_bottom_elt
    store_top_elt = HNN.store_top_elt
    store_bottom_elt = HNN.store_bottom_elt

    # pumps
    dist_pump = HNN.dist_pump
    store_pump = HNN.store_pump


    # required pipe temperatures
    dist_swt = HNN.dist_swt
    dist_rwt = HNN.dist_rwt
    hp_lwt = HNN.hp_lwt
    hp_ewt = HNN.hp_ewt
    store_hot_pipe = HNN.store_hot_pipe
    store_cold_pipe = HNN.store_cold_pipe
    buffer_hot_pipe = HNN.buffer_hot_pipe
    buffer_cold_pipe = HNN.buffer_cold_pipe

    floor_swt = "floor-swt"
    floor_rwt = "floor-rwt" # why??

    # flows
    dist_flow =HNN.dist_flow
    store_flow = HNN.store_flow

    # buffer tank
    buffer = HNN.buffer

    # relays
    buffer_top_relay = "buffer-top-relay"
    buffer_bottom_relay = "buffer-bottom-relay"

    store_top_relay = "store-top-relay"
    store_bottom_relay = "store-bottom-relay"

    # Optional
    oat = HNN.oat


    def __init__(self, total_store_tanks: int, zone_list: Sequence[str]) -> None:

        self.tanks = Tanks(total_store_tanks).nodes
        self.zones = {
            zone: NolanZoneNodeNames(zone, idx + 1)
            for idx, zone in enumerate(zone_list)
        }




"""
Nolan node name vocabulary.

Design note
-----------

This class intentionally uses *composition/aliasing* rather than inheritance
to expose names from CoreNodeNames and HydronicSpaceheatNodeNames.

Example:
    primary_scada = CNN.primary_scada
    asset_power_meter = CNN.asset_power_meter

Why this pattern?

1. Layouts are not vocabularies.
   CoreNodeNames and HydronicSpaceheatNodeNames define reusable domain
   vocabularies. NolanNodeNames represents a specific *layout* that selects
   and assembles names from those vocabularies.

2. Prevent vocabulary leakage.
   Inheritance would implicitly expose every name defined in upstream
   vocabularies, even if the Nolan layout does not actually use them.

3. Preserve architectural layering.

       CoreNames
           ↓
       HydronicSpaceheatNames
           ↓
       NolanNames / House0Names (layout-specific assemblies)

4. Make layout code readable.

   Layout generators and actors can reference a single namespace:

       NN.primary_scada
       NN.asset_power_meter
       NN.zone["down"].ops_relay

   instead of mixing multiple vocabularies (CNN.*, HNN.*, etc.).

The small duplication introduced by aliasing is intentional and keeps the
layout vocabulary explicit and stable.
"""