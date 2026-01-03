from typing import Optional
from typing import Tuple

import rich
from gwsproto.data_classes.components.hubitat_tank_component import HubitatTankComponent

from gwsproto.enums import TelemetryName
from gwsproto.enums import ActorClass
from gwsproto.named_types.hubitat_gt import HubitatGt
from pydantic import BaseModel
from pydantic_extra_types.mac_address import MacAddress

from layout_gen import add_hubitat
from layout_gen import add_thermostat
from layout_gen import add_tank1
from layout_gen import FibaroGenCfg
from layout_gen import HubitatThermostatGenCfg
from layout_gen import LayoutDb
from layout_gen import StubConfig
from layout_gen import Tank1Cfg

from gwsproto.data_classes.hardware_layout import HardwareLayout

_sn = 0

def _dummy_sn() -> str:
    global _sn
    _sn += 1
    return str(_sn)

def _dummy_fib() -> FibaroGenCfg:
    return FibaroGenCfg(SN=_dummy_sn(), ZWaveDSK="NA")

_DEFAULT_POLL_PERIODS = (
    60.0,
    60.0,
    60.0,
    60.0,
    60.0,
)

class _TankDeviceTestConfig(BaseModel):
    Name: str
    DisplayName: str = ""
    DefaultPollPeriodSeconds: Optional[float] = None
    DevicePollPeriodSeconds: Tuple[float|None, float|None, float|None, float|None] = None, None, None, None
    RestExp: Tuple[float, float, float, float] = _DEFAULT_POLL_PERIODS

def test_tank_device_poll_period(tmp_path):

    db = LayoutDb(
        # existing_layout=LayoutIDMap.from_path(Path(__file__).parent.parent.joinpath("config/hardware-layout.json")),
        add_stubs=True,
        stub_config=StubConfig(),
    )

    hubitat = HubitatGt(
        Host="hubitat-dummy.local",
        MakerApiId=4,
        AccessToken="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        MacAddress=MacAddress("00:00:00:00:00:00"),
    )

    cfgs = [
        _TankDeviceTestConfig(
            Name="unset",
        ),
        _TankDeviceTestConfig(
            Name="default",
            DefaultPollPeriodSeconds=1.0,
            RestExp=(1.0, 1.0, 1.0, 1.0),
        ),
        _TankDeviceTestConfig(
            Name="one-explicit",
            DevicePollPeriodSeconds=(1.0, None, None, None),
            RestExp=(1.0, 60.0, 60.0, 60.0),
        ),
        _TankDeviceTestConfig(
            Name="mixed",
            DefaultPollPeriodSeconds=1.0,
            DevicePollPeriodSeconds=(2.0, None, None, None),
            RestExp=(2.0, 1.0, 1.0, 1.0),
        ),
    ]

    for cfg in cfgs:
        tank_gen_cfg = Tank1Cfg(
            NodeName=cfg.Name,
            InHomeName=cfg.Name,
            SN=_dummy_sn(),
            DeviceIds=(1, 2, 3, 4),
            DefaultPollPeriodSeconds=cfg.DefaultPollPeriodSeconds,
            DevicePollPeriodSeconds=cfg.DevicePollPeriodSeconds,
        )
        cfg.DisplayName = tank_gen_cfg.component_alias()
        add_tank1(
            db,
            fibaro_a=_dummy_fib(),
            fibaro_b=_dummy_fib(),
            hubitat=hubitat,
            tank=tank_gen_cfg,
        )

    d = db.dict()
    errors = []
    def _err_str(name: str, field: str, exp: float, got: float) -> str:
        return (
            f"ERROR with cfg {name}  {field}. "
            f"Exp: {exp}  "
            f"Got: {got}"
        )
    tanks = []
    for cfg in cfgs:
        found = False
        for tankcj in d["OtherComponents"]:
            if "Tank" in tankcj:
                found = True
                tanks.append(tankcj)
                if tankcj["DisplayName"] == cfg.DisplayName:
                    tankj = tankcj["Tank"]
                    if cfg.DefaultPollPeriodSeconds is None:
                        if  "DefaultPollPeriodSeconds" in tankj:
                            errors.append(
                                _err_str(
                                    cfg.Name, "DefaultPollPeriodSeconds",
                                    cfg.DefaultPollPeriodSeconds,
                                    "DefaultPollPeriodSeconds",
                                )
                            )
                    elif cfg.DefaultPollPeriodSeconds != tankj["DefaultPollPeriodSeconds"]:
                        errors.append(
                            _err_str(
                                cfg.Name, "DefaultPollPeriodSeconds",
                                cfg.DefaultPollPeriodSeconds,
                                tankj["DefaultPollPeriodSeconds"],
                            )
                        )
                    for i, devicej in enumerate(tankj["Devices"]):
                        if cfg.DevicePollPeriodSeconds[i] is None:
                            if "PollPeriodSeconds" in devicej:
                                errors.append(
                                _err_str(
                                    f"{cfg.Name} layout device {i}", "PollPeriodSeconds",
                                    cfg.DefaultPollPeriodSeconds[i],
                                    "PollPeriodSeconds",
                                )
                            )
                        elif str(cfg.DevicePollPeriodSeconds[i])!= str(devicej["PollPeriodSeconds"]):
                            errors.append(
                                _err_str(
                                    f"{cfg.Name} layout device {i}", "PollPeriodSeconds",
                                    cfg.DevicePollPeriodSeconds[i],
                                    devicej["PollPeriodSeconds"],
                                )
                            )
        if not found:
            errors.append(f"<{cfg.DisplayName}> not found")

    layout_path = tmp_path / "hardware-layout.json"
    db.write(layout_path)

    load_errors = []
    layout = HardwareLayout.load(
        layout_path,
        raise_errors=True,
        errors=load_errors,
    )

    if load_errors:
        for error in load_errors:
            rich.print(error)
        raise ValueError(str(load_errors))

    for cfg in cfgs:
        component = layout.component(cfg.Name)
        assert isinstance(component, HubitatTankComponent)

        # rich.print(component.devices)
        for i, device in enumerate(component.devices):
            if str(cfg.RestExp[i]) != str(device.rest.poll_period_seconds):
                errors.append(
                    _err_str(
                        f"{cfg.Name} rest device {i}", "poll_period_seconds",
                        cfg.RestExp[i],
                        device.rest.poll_period_seconds,
                    )
                )
    s = ""
    if errors:
        s = f"Found {len(errors)} errors\n"
        for error in errors:
            s += f"\t{error}\n"
        print(s)
        rich.print(tanks)
    assert not s

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

