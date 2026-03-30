"""
Quick local sanity check for the `I2cThermistorReader` integration.

By default this script loads the layout pointed to by `SCADA_PATHS__HARDWARE_LAYOUT`
from the active `.env` / SCADA settings, so it follows the same layout selection
you are about to run under SCADA. You can still override that with `--layout`.

OFI:
- Promote this into a small reusable test harness that can boot selected actors
  from a real layout with lightweight fake hardware adapters.
- Move the fake services / fake I2C modules into shared test utilities once the
  broader actor test strategy is ready.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import types
from pathlib import Path
from typing import Any, Optional

import dotenv
from result import Ok

from actors.config import ScadaSettings
from actors.i2c_thermistor_reader import I2cThermistorReader
from actors.scada_data import ScadaData
from actors.scada_interface import ScadaInterface
from gwsproto.data_classes.house_0_layout import House0Layout
from gwsproto.named_types import Glitch, SyncedReadings
from scada_app_interface import ScadaAppInterface


REPO_ROOT = Path(__file__).resolve().parents[1]


class DummyLogger:
    def error(self, msg: str) -> None:
        print(msg)


class DummyPrimeActor(ScadaInterface):
    LOCAL_MQTT = "local_mqtt"
    ADMIN_MQTT = "admin"

    def __init__(self, data: ScadaData):
        self._data = data

    @classmethod
    def instantiate(cls, name: str, services: Any, **constructor_args: Any) -> "DummyPrimeActor":
        raise NotImplementedError("DummyPrimeActor is constructed directly in this script")

    @property
    def data(self) -> ScadaData:
        return self._data

    @property
    def contract_handler(self) -> Any:
        return None

    @property
    def name(self) -> str:
        return "s"

    @property
    def node(self) -> Any:
        return None

    def init(self) -> None:
        return None

    def process_message(self, message: Any) -> Ok[bool]:
        return Ok(True)

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    async def join(self) -> None:
        return None

    @property
    def monitored_names(self) -> list[Any]:
        return []

    def _send(self, message: Any) -> None:
        return None


class DummyServices(ScadaAppInterface):
    def __init__(self, layout: House0Layout, settings: ScadaSettings):
        self._layout = layout
        self._settings = settings
        self._data = ScadaData(settings, layout)
        self._prime_actor = DummyPrimeActor(self._data)
        self._logger = DummyLogger()
        self.sent_messages: list[Any] = []
        self.upstream_payloads: list[Any] = []
        self.published_messages: list[tuple[str, Any, Any]] = []
        self.tasks: list[Any] = []
        self._publication_name = "s"

    @property
    def settings(self) -> ScadaSettings:
        return self._settings

    @property
    def prime_actor(self) -> DummyPrimeActor:
        return self._prime_actor

    @property
    def scada(self) -> DummyPrimeActor:
        return self._prime_actor

    @property
    def hardware_layout(self) -> House0Layout:
        return self._layout

    @property
    def logger(self) -> DummyLogger:
        return self._logger

    @property
    def stats(self) -> Any:
        return None

    @property
    def publication_name(self) -> str:
        return self._publication_name

    @property
    def subscription_name(self) -> str:
        return "s"

    @property
    def upstream_client(self) -> str:
        return "gridworks_mqtt"

    @property
    def downstream_client(self) -> str:
        return "local_mqtt"

    def add_communicator(self, communicator: Any) -> None:
        return None

    def get_communicator(self, name: str) -> Optional[Any]:
        return None

    def get_communicator_as_type(self, name: str, type_: Any) -> Optional[Any]:
        return None

    def get_communicator_names(self) -> set[str]:
        return {"s", "derived-generator", "gw108-thermistor-reader"}

    def send(self, message: Any) -> None:
        self.sent_messages.append(message)

    async def await_processing(self, message: Any) -> Any:
        return Ok(True)

    def send_threadsafe(self, message: Any) -> None:
        self.send(message)

    def wait_for_processing_threadsafe(self, message: Any) -> Any:
        return Ok(True)

    def add_task(self, task: Any) -> None:
        self.tasks.append(task)

    @property
    def async_receive_queue(self) -> None:
        return None

    @property
    def event_loop(self) -> None:
        return None

    @property
    def io_loop_manager(self) -> Any:
        return None

    def add_web_server_config(self, name: str, host: str, port: int, **kwargs: Any) -> None:
        return None

    def add_web_route(
        self,
        server_name: str,
        method: str,
        path: str,
        handler: Any,
        **kwargs: Any,
    ) -> None:
        return None

    def get_web_server_route_strings(self) -> dict[str, list[str]]:
        return {}

    def get_web_server_configs(self) -> dict[str, Any]:
        return {}

    def generate_event(self, event: Any) -> Any:
        return Ok(True)

    def get_external_watchdog_builder_class(self) -> type[Any]:
        return type("DummyWatchdogBuilder", (), {})

    def add_callbacks(self, callback: Any) -> int:
        return 0

    def remove_callbacks(self, callbacks_id: int) -> None:
        return None

    def publish_upstream(self, payload: Any) -> None:
        self.upstream_payloads.append(payload)
        return None

    def publish_message(
        self,
        link_name: str,
        message: Any,
        qos: Any = None,
        context: Any = None,
        *,
        topic: str = "",
        use_link_topic: bool = False,
    ) -> None:
        self.published_messages.append((link_name, message, qos))
        return None


class FakeAnalogIn:
    voltages_by_pin: dict[str, float] = {}
    exceptions_by_pin: dict[str, BaseException] = {}

    def __init__(self, adc: Any, pin: str):
        self.pin = pin

    @property
    def voltage(self) -> float:
        if self.pin in self.exceptions_by_pin:
            raise self.exceptions_by_pin[self.pin]
        return self.voltages_by_pin[self.pin]


def install_fake_i2c_modules(*, fail_init: bool = False) -> contextlib.AbstractContextManager[None]:
    @contextlib.contextmanager
    def _manager() -> Any:
        original_modules = {
            name: sys.modules.get(name)
            for name in [
                "board",
                "adafruit_ads1x15",
                "adafruit_ads1x15.ads1115",
                "adafruit_ads1x15.analog_in",
            ]
        }
        try:
            board = types.ModuleType("board")

            def fake_i2c() -> object:
                if fail_init:
                    raise RuntimeError("simulated i2c init failure")
                return object()

            board.I2C = fake_i2c

            adafruit_pkg = types.ModuleType("adafruit_ads1x15")
            ads1115 = types.ModuleType("adafruit_ads1x15.ads1115")

            class FakeADS1115:
                def __init__(self, i2c: Any, address: int):
                    self.i2c = i2c
                    self.address = address

            ads1115.ADS1115 = FakeADS1115
            ads1115.P0 = "P0"
            ads1115.P1 = "P1"
            ads1115.P2 = "P2"
            ads1115.P3 = "P3"

            analog_in = types.ModuleType("adafruit_ads1x15.analog_in")
            analog_in.AnalogIn = FakeAnalogIn

            sys.modules["board"] = board
            sys.modules["adafruit_ads1x15"] = adafruit_pkg
            sys.modules["adafruit_ads1x15.ads1115"] = ads1115
            sys.modules["adafruit_ads1x15.analog_in"] = analog_in
            yield
        finally:
            for name, module in original_modules.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

    return _manager()


def make_services(layout_path: Path) -> DummyServices:
    layout = House0Layout.load(layout_path)
    settings = ScadaSettings(is_simulated=False)
    return DummyServices(layout, settings)


def default_layout_path() -> Path:
    env_file = dotenv.find_dotenv(".env", usecwd=True)
    settings = ScadaSettings(_env_file=env_file if env_file else None, is_simulated=False)
    return Path(settings.paths.hardware_layout).resolve()


def latest_glitch(services: DummyServices) -> Glitch:
    glitch = services.upstream_payloads[-1]
    assert isinstance(glitch, Glitch)
    return glitch


def latest_synced(services: DummyServices) -> SyncedReadings:
    payload = services.sent_messages[-1].Payload
    assert isinstance(payload, SyncedReadings)
    return payload


def run_success_case(layout_path: Path) -> None:
    FakeAnalogIn.voltages_by_pin = {"P0": 1.50, "P1": 1.55, "P2": 1.60}
    FakeAnalogIn.exceptions_by_pin = {}
    with install_fake_i2c_modules():
        services = make_services(layout_path)
        actor = I2cThermistorReader("gw108-thermistor-reader", services)
        for cfg in actor.device_configs.values():
            changed, microvolts, temp_c_x100 = actor.read_inputs(cfg)
            assert changed
            assert microvolts is not None
            assert temp_c_x100 is not None
        actor._publish()

    synced = latest_synced(services)
    expected_channels = {
        "zone1-bedrooms-gw-temp",
        "zone1-bedrooms-gw-microvolts",
        "zone2-living-rm-gw-temp",
        "zone2-living-rm-gw-microvolts",
        "zone4-garage-gw-temp",
        "zone4-garage-gw-microvolts",
    }
    assert set(synced.ChannelNameList) == expected_channels
    assert all(actor.latest_temp_c_x100[ch] is not None for ch in actor.device_configs)


def run_read_failure_case(layout_path: Path) -> None:
    FakeAnalogIn.voltages_by_pin = {"P0": 1.50, "P1": 1.55, "P2": 1.60}
    FakeAnalogIn.exceptions_by_pin = {"P1": RuntimeError("simulated read failure")}
    with install_fake_i2c_modules():
        services = make_services(layout_path)
        actor = I2cThermistorReader("gw108-thermistor-reader", services)
        bad_cfg = actor.device_configs["zone2-living-rm-gw-temp"]
        changed, microvolts, temp_c_x100 = actor.read_inputs(bad_cfg)

    assert changed is False
    assert microvolts is None
    assert temp_c_x100 is None
    glitch = latest_glitch(services)
    assert glitch.Summary == "i2c-thermistor-read-failed"
    assert "zone2-living-rm-gw-temp" in glitch.Details


def run_init_failure_case(layout_path: Path) -> None:
    FakeAnalogIn.voltages_by_pin = {}
    FakeAnalogIn.exceptions_by_pin = {}
    with install_fake_i2c_modules(fail_init=True):
        services = make_services(layout_path)
        actor = I2cThermistorReader("gw108-thermistor-reader", services)

    assert actor.adc_by_channel == {}
    glitch = latest_glitch(services)
    assert glitch.Summary == "i2c-thermistor-reader-init-failed"


def run_shorted_case(layout_path: Path) -> None:
    FakeAnalogIn.voltages_by_pin = {"P0": 0.005, "P1": 1.55, "P2": 1.60}
    FakeAnalogIn.exceptions_by_pin = {}
    with install_fake_i2c_modules():
        services = make_services(layout_path)
        actor = I2cThermistorReader("gw108-thermistor-reader", services)
        bad_cfg = actor.device_configs["zone1-bedrooms-gw-temp"]
        changed, microvolts, temp_c_x100 = actor.read_inputs(bad_cfg)

    assert changed is False
    assert microvolts is None
    assert temp_c_x100 is None
    glitch = latest_glitch(services)
    assert glitch.Summary == "i2c-thermistor-shorted"
    assert "shorted thermistor" in glitch.Details


def run_broken_case(layout_path: Path) -> None:
    FakeAnalogIn.voltages_by_pin = {"P0": 3.3, "P1": 1.55, "P2": 1.60}
    FakeAnalogIn.exceptions_by_pin = {}
    with install_fake_i2c_modules():
        services = make_services(layout_path)
        actor = I2cThermistorReader("gw108-thermistor-reader", services)
        bad_cfg = actor.device_configs["zone1-bedrooms-gw-temp"]
        changed, microvolts, temp_c_x100 = actor.read_inputs(bad_cfg)

    assert changed is False
    assert microvolts is None
    assert temp_c_x100 is None
    glitch = latest_glitch(services)
    assert glitch.Summary == "i2c-thermistor-broken"
    assert "indicates a broken or missing thermistor" in glitch.Details


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--layout",
        type=Path,
        default=None,
        help="Path to layout JSON. Defaults to SCADA_PATHS__HARDWARE_LAYOUT from .env",
    )
    args = parser.parse_args()
    layout_path = args.layout.resolve() if args.layout else default_layout_path()

    run_success_case(layout_path)
    print("PASS success-case: channels populated and synced reading emitted")

    run_read_failure_case(layout_path)
    print("PASS read-failure-case: exception contained and warning emitted")

    run_shorted_case(layout_path)
    print("PASS shorted-case: shorted thermistor warning emitted")

    run_broken_case(layout_path)
    print("PASS broken-case: broken thermistor warning emitted")

    run_init_failure_case(layout_path)
    print("PASS init-failure-case: init exception contained and warning emitted")

    print(f"PASS all sanity checks for {layout_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
