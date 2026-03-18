from dataclasses import dataclass
from gwsproto.enums import FlowManifoldVariant


@dataclass
class House0StubConfig:
    flow_manifold_variant: FlowManifoldVariant = FlowManifoldVariant.NolanHouse
    use_sieg_loop: bool = False
    ltn_gnode_alias: str = "ltn.orange"
    terminal_asset_alias: str | None = None
    scada_display_name: str = "Dummy Orange Scada"
    add_stub_power_meter: bool = True
    power_meter_cac_alias: str = "Dummy Power Meter Cac"
    power_meter_component_alias: str = "Dummy Power Meter Component"
    power_meter_node_display_name: str = "Dummy Power Meter"
    boost_element_display_name: str = "Dummy Boost Element"
    