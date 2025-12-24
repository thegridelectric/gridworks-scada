import math
import time
from typing import Dict, List, Optional

# noinspection PyUnresolvedReferences
import adafruit_ads1x15.ads1115 as ADS
# noinspection PyUnresolvedReferences
import board
# noinspection PyUnresolvedReferences
import busio
from actors.config import ScadaSettings
# noinspection PyUnresolvedReferences
from adafruit_ads1x15.analog_in import AnalogIn
from drivers.driver_result import DriverOutcome
from drivers.multipurpose_sensor.multipurpose_sensor_driver import \
    MultipurposeSensorDriver
from gwsproto.enums import LogLevel
from gwproto.data_classes.components.ads111x_based_component import \
    Ads111xBasedComponent
from gwproto.data_classes.data_channel import DataChannel
from gwproto.enums import MakeModel, TelemetryName
from gwproto.enums import ThermistorDataMethod
from result import Err, Ok, Result

# TODO: sense this and update it in synth channels
PI_VOLTAGE = 4.85

# Anything below about -30 C will read incorrectly
OPEN_VOLTAGE = PI_VOLTAGE - 0.15
THERMISTOR_T0_DEGREES_KELVIN = 298
# NTC THermistors are 10 kOhms at 25 deg C
THERMISTOR_R0_OHMS = 10000
# NTC Thermistors have a "rated beta" on their data sheet
THERMISTOR_BETA = 3977
# Then, there is our pull-up resistor
VOLTAGE_DIVIDER_R_OHMS = 10000

# TODO: add to component
EXP_ALPHA = 0.2
class GridworksTsnap1_MultipurposeSensorDriver(MultipurposeSensorDriver):
    # gives a range up to +/- 6.144V
    MAX_BACKOFF_SECONDS: float = 60
    ERROR_BACKOFF_SECONDS: float = 5
    ADS_GAIN = 0.6666666666666666
    SUPPORTED_TELEMETRIES = {
        TelemetryName.WaterTempCTimes1000,
        TelemetryName.AirTempCTimes1000,
    }
    MAX_READING_AGE_SEC = 30

    ads: dict[int, ADS]
    i2c: busio.I2C
    initialization_failed: Dict[int, bool]

    def __init__(self, component: Ads111xBasedComponent, settings: ScadaSettings):
        """
        Each Ads111xBasedCac is comprised of 1-4 4-channel Ads 1115 i2c devices, each
        of which has a hex address
        GridWorks TSnap1 has 12 terminal screwblocks, channels 1-12, that expect analog NTC
        Thermistors with R0= 10 kOhhms. These go to 3 4-channel Ads 1115 i2c devices:
        Ads1: channels 1-4
        Ads2: channels 5-8
        Ads3: channels 9-12

        See https://drive.google.com/drive/u/0/folders/1xmUr6kwHAQ2DW8I5GsiIQHHLGnM2ybX- for more
        TSNap channel information

        See https://drive.google.com/drive/u/0/folders/1KySP9BqT8F-sH8fgEvb9O3x_CTVAt71h for
        the Texas Instrument ADS1115 datasheet
        """
        super(GridworksTsnap1_MultipurposeSensorDriver, self).__init__(
            component=component, settings=settings
        )
        models: List[MakeModel] = [
            MakeModel.GRIDWORKS__TSNAP1,
        ]
        if component.cac.MakeModel not in models:
            raise Exception(
                f"Expected make model in {models}, got {component.cac.MakeModel}"
            )
        self.my_telemetry_names = component.cac.TelemetryNameList
        if set(self.my_telemetry_names) != {
            TelemetryName.WaterTempCTimes1000,
            TelemetryName.AirTempCTimes1000,
        }:
            raise Exception(
                "Expect AirTempCTimes1000 and AirTempFTimes1000 for AdsCac "
                "TelemetryNameList!"
            )
        c = component.gt
        self.terminal_block_idx_list = [tc.TerminalBlockIdx for tc in c.ConfigList]
        self.telemetry_name_list = component.cac.TelemetryNameList

        self.ads_address = {
            i: address for i, address in enumerate(component.cac.AdsI2cAddressList)
        }
        self.ads = {}
        self.initialization_failed = {}
        self._curr_connect_delay = 0
        # Track last warning time per channel
        self._last_warning_time: Dict[str, float] = {}  # data channel name as key
        self._warning_delays: Dict[str, float] = {}  # data channel name as key
        self._last_valid_reading_time: Dict[str, float] = {}  # channel name -> timestamp
        self._last_valid_reading: Dict[str, float] = {}  # channel name -> reading

        # In GridworksTsnap1_MultipurposeSensorDriver.__init__
        self.data_processing_method: Dict[str, ThermistorDataMethod] = {
            config.ChannelName: config.DataProcessingMethod 
            for config in component.gt.ConfigList
        }


        # Track the exponential moving average state
        self.exp_avg_state: Dict[str, Optional[float]] = {
            config.ChannelName: None 
            for config in component.gt.ConfigList
        }
        # Standard alpha value for EMA - could make configurable
        self.exp_avg_alpha = EXP_ALPHA # Higher alpha = more weight to recent values

    def start(self) -> Result[DriverOutcome[bool], Exception]:
        driver_init_outcome = DriverOutcome(True)

        try:
            self.i2c = busio.I2C(board.SCL, board.SDA)
        except BaseException as e:
            for idx in self.ads_address:
                self.initialization_failed[idx] = True
            driver_init_outcome.value = False
            driver_init_outcome.add_comment(level=LogLevel.Critical, msg=str(e))
            return Ok(driver_init_outcome)

        for idx, addr in self.ads_address.items():
            self.initialization_failed[idx] = False
            try:
                ads1115 = ADS.ADS1115(address=addr, i2c=self.i2c)
                ads1115.gain = self.ADS_GAIN
            except BaseException as e:
                driver_init_outcome.add_comment(
                    level=LogLevel.Critical,
                    msg=f"TSnap Address {addr} (chip {idx}) is missing: {e}",
                )
                driver_init_outcome.value = False
                self.initialization_failed[idx] = True
                continue  # skip to next iteration
            self.ads[idx] = ads1115

        return Ok(driver_init_outcome)

    def _should_skip_for_backoff(self, channel_name: str, now: float) -> bool:
        """
        Check if we should skip reading this channel due to being in a backoff period.
        Also initializes warning tracking for new channels.
        """
        # Initialize warning tracking for this channel if needed
        if channel_name not in self._last_warning_time:
            self._last_warning_time[channel_name] = 0
            self._warning_delays[channel_name] = 0
            return False

        # Only skip if we've had recent warnings and are within backoff period
        if self._warning_delays[channel_name] > 0:  # Has had warnings
            return (
                now - self._last_warning_time[channel_name]
            ) <= self._warning_delays[channel_name]

        return False

    def apply_exp_weighted_avg(self, channel_name: str, new_voltage: float) -> float:
        """Apply exponential weighted moving average to voltage reading"""
        if self.data_processing_method[channel_name] != ThermistorDataMethod.BetaWithExponentialAveraging:
            return new_voltage

        if self.exp_avg_state[channel_name] is None:
            self.exp_avg_state[channel_name] = new_voltage
            return new_voltage

        # EMA formula: new_avg = alpha * new_value + (1-alpha) * old_avg
        avg = (self.exp_avg_alpha * new_voltage + 
            (1 - self.exp_avg_alpha) * self.exp_avg_state[channel_name])
        self.exp_avg_state[channel_name] = avg
        return avg

    def read_voltage(self, ch: DataChannel) -> Result[DriverOutcome[float], Exception]:
        """Read voltage from the specified channel.

        A None value with no comments indicates reading was skipped (e.g. during backoff).
        A None value with comments indicates reading was attempted but failed.
        A float value indicates successful reading, though there may still be comments.
        """
        output = DriverOutcome[float](None)
        now = time.time()

        if self._should_skip_for_backoff(ch.Name, now):
            return Ok(output)

        cfg = next(
            (cfg for cfg in self.component.gt.ConfigList if cfg.ChannelName == ch.Name),
            None,
        )
        i = int((cfg.TerminalBlockIdx - 1) / 4)

        if self.initialization_failed[i]:
            self._warning_delays[ch.Name] = self.ERROR_BACKOFF_SECONDS
            output.add_comment(
                level=LogLevel.Warning,
                msg=f"Missing i2c addr {self.ads_address[i]} | Channel {ch.Name} | Terminal {cfg.TerminalBlockIdx}",
            )
            return Ok(output)

        pin = [ADS.P0, ADS.P1, ADS.P2, ADS.P3][(cfg.TerminalBlockIdx - 1) % 4]
        use_stale = False
        try:
            channel = AnalogIn(self.ads[i], pin)
            voltage = channel.voltage
        except OSError as e:
            output.add_comment(
                level=LogLevel.Warning,
                msg=f"I2C read failed | Channel {ch.Name} | Terminal {cfg.TerminalBlockIdx} | Error: {str(e)}",
            )
            self._handle_read_failure(ch.Name, now)
            return Ok(output)

        if voltage >= PI_VOLTAGE - 0.1: # sometimes it'll be be high from random noise
            output.add_comment(
                level=LogLevel.Warning,
                msg=f"Open Thermistor reading AND bad max voltage! | {ch.Name} (term {cfg.TerminalBlockIdx}) read {voltage:.3f}V | CODE PI MAX {PI_VOLTAGE}V",
            )
            self._handle_read_failure(ch.Name, now)
            use_stale = True
        elif voltage >= OPEN_VOLTAGE:
            output.add_comment(
                level=LogLevel.Info,
                msg=f"Open Thermistor reading! | Channel {ch.Name} | Terminal {cfg.TerminalBlockIdx} | ",
            )
            self._handle_read_failure(ch.Name, now)
            use_stale = True
        elif voltage == 0:
            output.add_comment(
                level=LogLevel.Warning,
                msg=f"Thermistor short!| Channel {ch.Name} | Terminal {cfg.TerminalBlockIdx}",
            )
            self._handle_read_failure(ch.Name, now)
            use_stale = True
        else:
            if self.data_processing_method[ch.Name] == ThermistorDataMethod.BetaWithExponentialAveraging:
                output.value = self.apply_exp_weighted_avg(ch.Name, voltage)
            elif self.data_processing_method[ch.Name] == ThermistorDataMethod.SimpleBeta:
                output.value = voltage
            else:
                output.value = voltage # SimpleBeta is the fallback. TODO: let this be known
            self._warning_delays[ch.Name] = 0
            self._last_valid_reading[ch.Name] = voltage  
            self._last_valid_reading_time[ch.Name] = now 
        
        # if the ADS burped and we have a valid reading:
        if use_stale and ch.Name in self._last_valid_reading:
            # use it if it isn't too stale
            if now - self._last_valid_reading_time[ch.Name] < self.MAX_READING_AGE_SEC:
                    output.value = self._last_valid_reading[ch.Name]
            # or add a warning that this channel has been out to lunch for a while
            else:
                output.add_comment(
                    level=LogLevel.Warning,
                    msg=f"Data too stale for {ch.Name} - last valid reading {(now - self._last_valid_reading_time[ch.Name])/60:.1f} minutes ago"
                )

        return Ok(output)

    def _handle_read_failure(self, channel_name: str, now: float) -> None:
        """Update warning tracking when a read fails"""
        self._last_warning_time[channel_name] = now
        if self._warning_delays[channel_name] == 0:
            self._warning_delays[channel_name] = 1
        else:
            self._warning_delays[channel_name] = min(
                self._warning_delays[channel_name] * 2, self.MAX_BACKOFF_SECONDS
            )

    def read_telemetry_values(
        self, data_channels: List[DataChannel]
    ) -> Result[DriverOutcome[Dict[str, Optional[int]]], Exception]:  # DataChannel name
        """Reads temperature values for specified channels.
        If a data channel is in backoff, channel not included in the dict

        Returns DriverOutcome with:
        - value as dict mapping channel names to their temperature readings in appropriate units
        - comments for any issues encountered during reading
        """

        outcome = DriverOutcome[Dict[str,Optional[int]]]({})

        for ch in data_channels:
            read_result = self.read_voltage(ch)
            if read_result.is_ok():
                read_outcome = read_result.value
                # Pass through any comments from voltage reading
                outcome.comments.extend(read_outcome.comments)

                if read_outcome.value is not None:
                    if ch.TelemetryName not in {
                        TelemetryName.AirTempCTimes1000,
                        TelemetryName.AirTempFTimes1000,
                        TelemetryName.WaterTempCTimes1000,
                        TelemetryName.WaterTempFTimes1000,
                    }:
                        outcome.add_comment(
                            level=LogLevel.Warning,
                            msg=f"Unrecognized TelemetryName {ch.TelemetryName} for {ch.Name}!",
                        )
                        continue  # go onto the next channel
                    if ch.TelemetryName in {
                        TelemetryName.AirTempCTimes1000,
                        TelemetryName.WaterTempCTimes1000,
                    }:
                        convert_voltage_result = self.voltage_to_c(read_outcome.value)
                    elif ch.TelemetryName in {
                        TelemetryName.AirTempFTimes1000,
                        TelemetryName.WaterTempFTimes1000,
                    }:
                        convert_voltage_result = self.voltage_to_f(read_outcome.value)
                    if convert_voltage_result.is_ok():
                        outcome.value[ch.Name] = int(
                            convert_voltage_result.value * 1000
                        )
                    else:
                        outcome.add_comment(
                            level=LogLevel.Warning,
                            msg=f"Temperature conversion failed | Channel {ch.Name} | Voltage {read_outcome.value:.3f}V | Error: {convert_voltage_result.err()}",
                        )
                else:
                    outcome.value[ch.Name] = None

        return Ok(outcome)

    @classmethod
    def voltage_to_f(cls, voltage: float) -> Result[float, Exception]:
        """Calculate resistance from Beta function

        Thermistor data sheets typically provide the three parameters needed
        for the beta formula (R0, beta, and T0)
        "Under the best conditions, the beta formula is accurate to approximately
        +/- 1 C over the temperature range of 0 to 100C
        """
        temp_c = cls.voltage_to_c(voltage)
        if temp_c.is_ok():
            temp_f = 32 + 8 * temp_c / 5
            return Ok(temp_f)
        else:
            return temp_c

    @classmethod
    def voltage_to_c(cls, voltage: float) -> Result[float, Exception]:
        """Calculate resistance from Beta function

        Thermistor data sheets typically provide the three parameters needed
        for the beta formula (R0, beta, and T0)
        "Under the best conditions, the beta formula is accurate to approximately
        +/- 1 C over the temperature range of 0 to 100C

        Could consider upgrading to Steinhart-Hart:
        https://www.newport.com/medias/sys_master/images/images/hdb/hac/8797291479070/TN-STEIN-1-Thermistor-Constant-Conversions-Beta-to-Steinhart-Hart.pdf

        """
        rd: int = int(VOLTAGE_DIVIDER_R_OHMS)
        r0: int = int(THERMISTOR_R0_OHMS)
        beta: int = int(THERMISTOR_BETA)
        t0: int = int(THERMISTOR_T0_DEGREES_KELVIN)
        # Calculate the resistance of the thermistor
        try:
            rt = rd * voltage / (PI_VOLTAGE - voltage)
        except Exception as e:
            return Err(Exception(f"Didn't get to therm resistance! {str(e)}"))

        # Calculate the temperature in degrees Celsius. Note that 273 is
        # 0 degrees Celsius as measured in Kelvin.

        try:
            temp_c = 1 / ((1 / t0) + (math.log(rt / r0) / beta)) - 273
            return Ok(temp_c)
        except Exception as e:
            return Err(Exception(f"Got to therm resistance={rt}: {str(e)}"))
