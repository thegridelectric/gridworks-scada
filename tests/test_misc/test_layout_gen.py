from gwsproto.enums import TelemetryName
from gwsproto.enums import ActorClass
from gwsproto.named_types.hubitat_gt import HubitatGt

from layout_gen import add_hubitat
from layout_gen import add_thermostat
from layout_gen.simulated_tanks import add_simulated_tanks
from layout_gen import HubitatThermostatGenCfg
from layout_gen import LayoutDb
from layout_gen import StubConfig

from gwsproto.data_classes.hardware_layout import HardwareLayout

_sn = 0

def _dummy_sn() -> str:
    global _sn
    _sn += 1
    return str(_sn)

def test_tank_device_capture_period(tmp_path):

    db = LayoutDb(
        # existing_layout=LayoutIDMap.from_path(Path(__file__).parent.parent.joinpath("config/hardware-layout.json")),
        add_stubs=True,
        stub_config=StubConfig(),
    )

    add_simulated_tanks(db) 

    # TODO: add more tank tests, including testing that they load as SimPicoTankModuleComponents


    layout_path = tmp_path / "hardware-layout.json"
    db.write(layout_path)

    load_errors = []
    HardwareLayout.load(
        layout_path,
        raise_errors=True,
        errors=load_errors,
    )

    

def test_hubitat():
    db = LayoutDb(
        add_stubs=True,
        stub_config=StubConfig(),
    )
    hubitat_mac_address = "00:00:00:0A:BB:cc"
    hubitat_component_id = db.component_id_by_alias(
        add_hubitat(
            db,
            HubitatGt(
                Host="hubitat-dummy.local",
                MakerApiId=4,
                AccessToken="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                MacAddress=hubitat_mac_address,
            )
        )
    )
    layout = HardwareLayout.load_dict(db.dict(), raise_errors=True)
    node = layout.node_from_component(
        hubitat_component_id
    )
    assert node is not None
    assert node.Name == "hubitat"
    assert node.component_id == hubitat_component_id
    assert node.actor_class == ActorClass.Hubitat

def test_honeywell_thermostat():
    db = LayoutDb(
        add_stubs=True,
        stub_config=StubConfig(),
    )

    zone_name = "garage"
    zone_idx = 1
    add_thermostat(
        db,
        HubitatThermostatGenCfg(
            zone_idx=zone_idx,
            zone_name=zone_name,
            thermostat_idx=zone_idx,
            hubitat=HubitatGt(
                Host="hubitat-dummy.local",
                MakerApiId=4,
                AccessToken="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                MacAddress="00:00:00:00:00:00",
            ),
            device_id=1
        ),
    )
    layout = HardwareLayout.load_dict(db.dict(), raise_errors=True)
    assert layout.node("zone1-garage-stat").actor_class == ActorClass.HoneywellThermostat
    assert layout.node("zone1-garage").actor_class == ActorClass.NoActor
    assert layout.channel("zone1-garage-set").AboutNodeName == "zone1-garage-stat"
    assert layout.channel("zone1-garage-set").CapturedByNodeName == "zone1-garage-stat"
    assert layout.channel("zone1-garage-set").TelemetryName == TelemetryName.AirTempFTimes1000
    assert layout.channel("zone1-garage-temp").AboutNodeName == "zone1-garage"
    assert layout.channel("zone1-garage-temp").CapturedByNodeName == "zone1-garage-stat"
    assert layout.channel("zone1-garage-temp").TelemetryName == TelemetryName.AirTempFTimes1000
    assert layout.channel("zone1-garage-state").AboutNodeName == "zone1-garage-stat"
    assert layout.channel("zone1-garage-state").CapturedByNodeName == "zone1-garage-stat"
    assert layout.channel("zone1-garage-state").TelemetryName == TelemetryName.ThermostatState



def test_flow_module_keeps_its_reference_component_id():
    """A flow module whose alias is in the reference layout keeps that
    ComponentId across a regen, for both the Hall and the Reed word."""
    from layout_gen import LayoutIDMap
    from layout_gen.flow import HallCfg, ReedCfg, add_flow

    hall = HallCfg(ActorNodeName="sieg-flow", HwUid="pico_4e6e35")
    reed = ReedCfg(ActorNodeName="dist-flow2", HwUid="pico_2a7e22")
    reference = LayoutIDMap()
    reference.add_component("30e25b97-60bf-40e3-870a-1ba80bf3b164", hall.component_display_name())
    reference.add_component("30d6a861-baa7-49fd-8033-771c0704469a", reed.component_display_name())

    db = LayoutDb(existing_layout=reference, add_stubs=True, stub_config=StubConfig())
    add_flow(db, hall)
    add_flow(db, reed)

    assert db.component_id_by_alias(hall.component_display_name()) == "30e25b97-60bf-40e3-870a-1ba80bf3b164"
    assert db.component_id_by_alias(reed.component_display_name()) == "30d6a861-baa7-49fd-8033-771c0704469a"
