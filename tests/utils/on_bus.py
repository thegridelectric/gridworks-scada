"""A device of a simulated board driven as a real board's is: through the
bus actor, onto the bus's fake chips. The app itself puts the plant link
behind a simulated board's devices, which has no chip to fail."""

from actors.i2c_thermistor_reader import I2cThermistorReader
from actors.relay import Relay
from actors.zero_ten_outputer import ZeroTenOutputer
from dac_drives import I2cDacDrive, resolve_dac_output
from plant import Device
from relay_drives import I2cRelayDrive, resolve_i2c_actuation
from scada_app import ScadaApp
from thermistor_inputs import Ads1115ThermistorInput, resolve_thermistor_adc


def put_behind(app: ScadaApp, node_name: str, device: Device) -> None:
    app.plant.device_by_node[node_name] = device


def relay_on_bus(app: ScadaApp, relay_name: str) -> Relay:
    node = app.hardware_layout.node(relay_name)
    assert node is not None
    put_behind(app, relay_name, I2cRelayDrive(resolve_i2c_actuation(app.hardware_layout, node)))
    return Relay(relay_name, app)


def outputer_on_bus(app: ScadaApp, name: str) -> tuple[ZeroTenOutputer, I2cDacDrive]:
    node = app.hardware_layout.node(name)
    assert node is not None
    drive = I2cDacDrive(resolve_dac_output(app.hardware_layout, node))
    put_behind(app, name, drive)
    return ZeroTenOutputer(name, app), drive


def reader_on_bus(app: ScadaApp, name: str) -> tuple[I2cThermistorReader, Ads1115ThermistorInput]:
    node = app.hardware_layout.node(name)
    assert node is not None
    adc = Ads1115ThermistorInput(resolve_thermistor_adc(app.hardware_layout, node))
    put_behind(app, name, adc)
    return I2cThermistorReader(name, app), adc
