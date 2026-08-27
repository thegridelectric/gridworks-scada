import asyncio
import math
import time
from typing import Sequence, TYPE_CHECKING


if TYPE_CHECKING:
    from adafruit_ads1x15.analog_in import AnalogIn

from result import Result

from gwproto.message import Message
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage

from actors.sh_node_actor import ShNodeActor

from gwsproto.named_types import (
    I2cThermistorChannelConfig,
    SingleReading, 
    SyncedReadings,
)
from gwsproto.data_classes.components import I2cThermistorReaderComponent
from gwsproto.property_format import SpaceheatName
from gwsproto.enums import TelemetryName, TempCalcMethod

from scada_app_interface import ScadaAppInterface
THERMISTOR_T0 = 298.15  # i.e. 25 degrees
THERMISTOR_R0_KOHMS = 10

class I2cThermistorReader(ShNodeActor):

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)

        component = self.node.component

        if not isinstance(component, I2cThermistorReaderComponent):
            raise ValueError(
                f"{self.name} expected I2cThermistorComponent, got {type(component)}"
            )

        self.component: I2cThermistorReaderComponent = component
        self.cfgs = self.component.gt.ConfigList

        self.device_configs: dict[SpaceheatName, I2cThermistorChannelConfig] = {}
        self.electrical_configs: dict[SpaceheatName, I2cThermistorChannelConfig] = {}
        self.electrical_cfg_by_device: dict[SpaceheatName, I2cThermistorChannelConfig]  = {}

        (
            self.device_configs,
            self.electrical_configs,
            self.electrical_cfg_by_device,
        ) = self._build_channel_maps()

        self._stop_requested = False
        self._active_warning_keys: set[str] = set()

        # Per-channel state
        self.adc_by_channel: dict[SpaceheatName, "AnalogIn"] = {}
        self.latest_microvolts: dict[SpaceheatName, int] = {} # by electrical channel name
        self.latest_temp_c_x100: dict[SpaceheatName, int] = {} # by device channel name
        self.last_reported_temp_c_x100: dict[SpaceheatName, int] = {}

        if self.settings.is_simulated:
            self.i2c = None
            self.adc = None
            self.adc_by_channel = {}
        else:
            import adafruit_ads1x15.ads1115 as ADS1115
            from adafruit_ads1x15.analog_in import AnalogIn
            import board

            try:
                self.i2c = board.I2C()
                self.adc = ADS1115.ADS1115(
                    self.i2c,
                    address=self.component.gt.AdcAddress
                )

                for cfg in self.electrical_configs.values():
                    try:
                        pin = getattr(ADS1115, cfg.AdcChannel)
                    except AttributeError:
                        raise ValueError(f"{self.name}: invalid AdcChannel {cfg.AdcChannel}")

                    self.adc_by_channel[cfg.ChannelName] = AnalogIn(self.adc, pin)
            except Exception as e:
                self.i2c = None
                self.adc = None
                self.adc_by_channel = {}
                self._send_warning_once(
                    "i2c-thermistor-reader-init-failed",
                    "i2c-thermistor-reader-init-failed",
                    str(e),
                )

    def _send_warning_once(self, key: str, summary: str, details: str = "") -> None:
        if key in self._active_warning_keys:
            return
        self._active_warning_keys.add(key)
        self.send_warning(summary=summary, details=details)

    def _clear_warning(self, key: str) -> None:
        self._active_warning_keys.discard(key)

    def _clear_latest_reading(
        self,
        device_name: SpaceheatName,
        electrical_name: SpaceheatName,
    ) -> None:
        self.latest_temp_c_x100.pop(device_name, None)
        self.latest_microvolts.pop(electrical_name, None)


    def _build_channel_maps(
        self,
    ) -> tuple[
        dict[SpaceheatName, I2cThermistorChannelConfig],
        dict[SpaceheatName, I2cThermistorChannelConfig],
        dict[SpaceheatName, I2cThermistorChannelConfig],
    ]:
        """
        Builds:
            - device_configs: device channel name → cfg
            - electrical_configs: electrical channel name → cfg
            - electrical_cfg_by_device: device channel name → electrical cfg
        """

        device_configs: dict[SpaceheatName, I2cThermistorChannelConfig] = {}
        electrical_configs: dict[SpaceheatName, I2cThermistorChannelConfig] = {}

        # --- classify configs ---
        for cfg in self.component.gt.ConfigList:
            if cfg.ChannelName not in self.layout.data_channels:
                raise ValueError(
                    f"{self.name}: channel {cfg.ChannelName} not found in layout"
                )

            ch = self.layout.data_channels[cfg.ChannelName]

            if ch.TelemetryName == TelemetryName.MicroVolts:
                electrical_configs[ch.Name] = cfg

            elif ch.TelemetryName == TelemetryName.CelsiusTimes100:
                device_configs[ch.Name] = cfg

            else:
                raise ValueError(
                    f"{self.name}: unsupported TelemetryName {ch.TelemetryName} "
                    f"for channel {ch.Name}"
                )

        # --- group electrical by AboutNodeName ---
        electrical_by_about: dict[SpaceheatName, SpaceheatName] = {}

        for ch_name in electrical_configs:
            ch = self.layout.data_channels[ch_name]
            about = ch.AboutNodeName

            if about in electrical_by_about:
                raise ValueError(
                    f"{self.name}: multiple electrical channels for AboutNodeName {about}"
                )

            electrical_by_about[about] = ch_name

        # --- map device → electrical ---
        electrical_cfg_by_device: dict[SpaceheatName, I2cThermistorChannelConfig] = {}

        for device_name, device_cfg in device_configs.items():
            device_ch = self.layout.data_channels[device_name]
            about = device_ch.AboutNodeName

            if about not in electrical_by_about:
                raise ValueError(
                    f"{self.name}: no electrical channel for AboutNodeName {about}"
                )

            electrical_name = electrical_by_about[about]
            electrical_cfg_by_device[device_name] = electrical_configs[electrical_name]

        return device_configs, electrical_configs, electrical_cfg_by_device

    def start(self):
        self.services.add_task(
            asyncio.create_task(self.main(), name=f"{self.name}-main")
        )
        self.log(f"I2cThermistorReader started at address {self.component.gt.AdcAddress}")

    def stop(self) -> None:
        self._stop_requested = True

    async def join(self) -> None:
        ...

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        ...

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, 120)]

    def read_inputs(
        self, device_cfg: I2cThermistorChannelConfig
    ) -> tuple[bool, int | None, int | None]:
        """
        Input: device (i.e. temp) cfg 
        Returns:
          changed (based on temperature delta)
          microvolts
          temp_c_x100
        """
        
        device_name = device_cfg.ChannelName
        electrical_cfg = self.electrical_cfg_by_device[device_name]
        electrical_name = electrical_cfg.ChannelName
        device_ch = self.layout.data_channels[device_name]
        
        if device_ch.TelemetryName != TelemetryName.CelsiusTimes100:
            raise ValueError("requires a device channel (that reads CelsiusTimes100)")

        read_warning_key = f"i2c-thermistor-read-{electrical_name}"
        invalid_warning_key = f"i2c-thermistor-invalid-{device_name}"
        short_warning_key = f"i2c-thermistor-short-{device_name}"
        broken_warning_key = f"i2c-thermistor-broken-{device_name}"

        if self.settings.is_simulated:
            volts = 0.2 # dummy
        else:
            chan = self.adc_by_channel.get(electrical_cfg.ChannelName)
            if chan is None:
                self._clear_latest_reading(device_name, electrical_name)
                self._send_warning_once(
                    read_warning_key,
                    "i2c-thermistor-read-failed",
                    f"{device_name}: ADC channel {electrical_cfg.ChannelName} unavailable",
                )
                return False, None, None
            try:
                volts = chan.voltage
            except Exception as e:
                self._clear_latest_reading(device_name, electrical_name)
                self._send_warning_once(
                    read_warning_key,
                    "i2c-thermistor-read-failed",
                    f"{device_name}: {e}",
                )
                return False, None, None
            self._clear_warning(read_warning_key)

        r_fixed = self.component.gt.SeriesResistanceKOhms
        v_ref = self.component.gt.AdcReferenceVolts

        if volts <= 0.01:
            self._clear_latest_reading(device_name, electrical_name)
            self._send_warning_once(
                short_warning_key,
                "i2c-thermistor-shorted",
                f"{device_name}: {volts:.6f} V indicates a shorted thermistor",
            )
            return False, None, None
        self._clear_warning(short_warning_key)

        if volts >= v_ref:
            self._clear_latest_reading(device_name, electrical_name)
            self._send_warning_once(
                broken_warning_key,
                "i2c-thermistor-broken",
                f"{device_name}: {volts:.6f} V indicates a broken or missing thermistor",
            )
            return False, None, None

        try:
            microvolts = int(volts * 1_000_000)
            r_therm = r_fixed * volts / (v_ref - volts)
            temp_c = self.temp_beta(device_cfg, r_therm)
            if temp_c <= 0:
                self._clear_latest_reading(device_name, electrical_name)
                self._send_warning_once(
                    broken_warning_key,
                    "i2c-thermistor-broken",
                    f"{device_name}: {volts:.6f} V implies {temp_c:.2f} C, indicating a broken or missing thermistor",
                )
                return False, None, None
            self._clear_warning(broken_warning_key)
            temp_c_x100 = int(temp_c * 100)
        except Exception as e:
            self._clear_latest_reading(device_name, electrical_name)
            self._send_warning_once(
                invalid_warning_key,
                "i2c-thermistor-invalid-reading",
                f"{device_name}: failed to convert reading ({e})",
            )
            return False, None, None

        # --- change detection uses temperature ---
        self.latest_microvolts[electrical_name] = microvolts
        self.latest_temp_c_x100[device_name] = temp_c_x100
        prev_temp = self.last_reported_temp_c_x100.get(device_name)
        if prev_temp is None:
            self.last_reported_temp_c_x100[device_name] = temp_c_x100
            return True, microvolts, temp_c_x100

        delta = abs(temp_c_x100 - prev_temp)
        threshold = device_cfg.AsyncCaptureDelta

        if threshold is None: # not reporting asynchronously
            changed = False
        else:
            changed = delta >= threshold
    
        if changed:
            self.last_reported_temp_c_x100[device_name] = temp_c_x100

        return changed, microvolts, temp_c_x100

    def temp_beta(self, cfg: I2cThermistorChannelConfig, r_therm_kohms: float) -> float:
        if self.component.gt.TempCalcMethod != TempCalcMethod.SimpleBeta:
            raise ValueError(
                f"Using temp_beta when TempCalcMethod is {self.component.gt.TempCalcMethod}"
            )
        t0, r0 = (
            THERMISTOR_T0,
            THERMISTOR_R0_KOHMS,
        )
        beta = cfg.ThermistorBeta
        r_therm = r_therm_kohms
        temp_c = 1 / ((1 / t0) + (math.log(r_therm / r0) / beta)) - 273

        return temp_c


    async def main(self):
        if not self.cfgs:
            self._send_warning_once(
                "i2c-thermistor-reader-no-config",
                "i2c-thermistor-reader-no-config",
                "",
            )
            return

        # assume uniform timing for now (first cfg)
        cfg0 = self.cfgs[0]

        poll_period = (
            cfg0.PollPeriodMs / 1000.0
            if cfg0.PollPeriodMs
            else 1
        )

        period = cfg0.CapturePeriodS
        next_capture_ts = ((int(time.time()) // period) + 1) * period

        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))

            for device_cfg in self.device_configs.values():
                try:
                    changed, _, _ = self.read_inputs(device_cfg)
                except Exception as e:
                    self._send_warning_once(
                        f"i2c-thermistor-loop-{device_cfg.ChannelName}",
                        "i2c-thermistor-read-failed",
                        f"{device_cfg.ChannelName}: {e}",
                    )
                    continue

                if changed:
                    try:
                        self._publish(device_cfg)
                    except Exception as e:
                        self._send_warning_once(
                            f"i2c-thermistor-publish-{device_cfg.ChannelName}",
                            "i2c-thermistor-publish-failed",
                            f"{device_cfg.ChannelName}: {e}",
                        )

            if time.time() >= next_capture_ts:
                try:
                    self._publish()
                except Exception as e:
                    self._send_warning_once(
                        "i2c-thermistor-periodic-publish-failed",
                        "i2c-thermistor-periodic-publish-failed",
                        str(e),
                    )
                now = time.time()
                while next_capture_ts <= now:
                    next_capture_ts += period

            sleep_s = min(poll_period, max(0, next_capture_ts - time.time()))
            await asyncio.sleep(sleep_s)

    def _publish(self, device_cfg: I2cThermistorChannelConfig | None = None):
        """
        If device_cfg is provided → publish that device channel (+ its electrical pair)
        If None → publish all device channels (+ electrical pairs)

        - Primary SCADA → SyncedReadings (temp + microvolts)
        - Derived Generator → SingleReading (temperature only)
        """

        if device_cfg is None:
            device_cfgs = self.device_configs.values()
        else:
            device_cfgs = [device_cfg]

        channel_name_list: list[SpaceheatName] = []
        value_list: list[int] = []

        now_ms = int(time.time() * 1000)

        for device_cfg in device_cfgs:
            device_name = device_cfg.ChannelName
            if device_name not in self.electrical_cfg_by_device:
                self._send_warning_once(
                    f"i2c-thermistor-publish-map-{device_name}",
                    "i2c-thermistor-publish-failed",
                    f"{device_name}: no electrical config mapped",
                )
                continue
            electrical_cfg = self.electrical_cfg_by_device[device_name]
            electrical_name = electrical_cfg.ChannelName

            # --- temperature ---
            if device_name not in self.latest_temp_c_x100:
                continue

            temp_val = self.latest_temp_c_x100[device_name]

            # add to SCADA bundle
            channel_name_list.append(device_name)
            value_list.append(temp_val)

            # send to derived generator (single reading, temperature only)
            if device_cfg.SendToDerived:
                self._send_to(
                    self.derived_generator,
                    SingleReading(
                        ChannelName=device_name,
                        Value=temp_val,
                        ScadaReadTimeUnixMs=now_ms,
                    ),
                )

            # --- microvolts (always to SCADA for now) ---
            if electrical_name in self.latest_microvolts:
                channel_name_list.append(electrical_name)
                value_list.append(self.latest_microvolts[electrical_name])

        if not channel_name_list:
            return

        # --- send to primary SCADA ---
        msg = SyncedReadings(
            ChannelNameList=channel_name_list,
            ValueList=value_list,
            ScadaReadTimeUnixMs=now_ms,
        )

        self._send_to(self.primary_scada, msg)
