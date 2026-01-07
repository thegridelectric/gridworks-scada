import time
import json
import pytz
import asyncio
import aiohttp
import math
import numpy as np
from typing import Optional, Sequence
from result import Ok, Result
from datetime import datetime,  timezone
from gwproto import Message

from gwsproto.data_classes.sh_node import ShNode
from gwsproto.named_types import SingleReading, SyncedReadings
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage

from actors.sh_node_actor import ShNodeActor
from gwsproto.enums import HomeAloneStrategy
from gwsproto.data_classes.house_0_names import H0N, H0CN
from gwsproto.named_types import (
    Ha1Params, HeatingForecast, ScadaParams,
    TankTempCalibration,
    TankTempCalibrationMap,
    WeatherForecast,
)
from scada_app_interface import ScadaAppInterface


class DerivedGenerator(ShNodeActor):
    MAIN_LOOP_SLEEP_SECONDS = 60
    GALLONS_PER_TANK = 119
    WATER_SPECIFIC_HEAT_KJ_PER_KG_C = 4.187
    GALLON_PER_LITER = 3.78541

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self._stop_requested: bool = False
        self.hardware_layout = self._services.hardware_layout

        self.elec_assigned_amount = None
        self.previous_time = None
        self.received_new_params: bool = False
        self.last_evaluated_strategy = 0
        self.first_required_energy_update_done: bool = False

        # House parameters in the .env file
        self.is_simulated = self.settings.is_simulated
        self.timezone = pytz.timezone(self.settings.timezone_str)
        self.latitude = self.settings.latitude
        self.longitude = self.settings.longitude

        # used by the rswt quad params calculator
        self._cached_params: Optional[Ha1Params] = None 
        self._rswt_quadratic_params: Optional[np.ndarray] = None 
    
        self.log(f"self.timezone: {self.timezone}")
        self.log(f"self.latitude: {self.latitude}")
        self.log(f"self.longitude: {self.longitude}")
        self.log(f"Params: {self.params}")
        self.log(f"self.is_simulated: {self.is_simulated}")
        self.weather_forecast: Optional[WeatherForecast] = None
        self.coldest_oat_by_month = [-3, -7, 1, 21, 30, 31, 46, 47, 28, 24, 16, 0]
        self.tmap: TankTempCalibrationMap = TankTempCalibrationMap.model_validate(getattr(self.node, "TankTempCalibrationMap"))
    
    @property
    def params(self) -> Ha1Params:
        return self.data.ha1_params
    
    @property
    def no_power_rswt(self) -> float:
        alpha = self.params.AlphaTimes10 / 10
        beta = self.params.BetaTimes100 / 100
        return -alpha/beta

    @property
    def rswt_quadratic_params(self) -> np.ndarray:
        """Property to get quadratic parameters for calculating heating power 
        from required source water temp, recalculating if necessary
        """
        if self.params != self._cached_params:
            intermediate_rswt = self.params.IntermediateRswtF
            dd_rswt = self.params.DdRswtF
            intermediate_power = self.params.IntermediatePowerKw
            dd_power = self.params.DdPowerKw
            x_rswt = np.array([self.no_power_rswt, intermediate_rswt, dd_rswt])
            y_hpower = np.array([0, intermediate_power, dd_power])
            A = np.vstack([x_rswt**2, x_rswt, np.ones_like(x_rswt)]).T
            self._rswt_quadratic_params = np.linalg.solve(A, y_hpower)
            self._cached_params = self.params
            self.log(f"Calculating rswt_quadratic_params: {self._rswt_quadratic_params}")
        
        if self._rswt_quadratic_params is None:
            raise Exception("_rswt_quadratic_params should have been set here!!")
        return self._rswt_quadratic_params

    def start(self) -> None:
        self.services.add_task(
            asyncio.create_task(self.main(), name="Synth Generator keepalive")
        )

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.MAIN_LOOP_SLEEP_SECONDS * 2.1)]
    
    async def main(self):
        async with aiohttp.ClientSession() as session:
            await self.main_loop(session)

    async def main_loop(self, session: aiohttp.ClientSession) -> None:
        self.log("SynthGen about to get forecasts")
        await self.get_forecasts(session)
        await asyncio.sleep(2)
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))

            if self.heating_forecast is None or time.time()>self.heating_forecast.Time[0] or self.received_new_params:
                await self.get_forecasts(session)
                self.received_new_params = False

            self.get_temperatures()
            if self.buffer_temps_available:
                self.update_usable_energy()
                if self.heating_forecast:
                    self.update_required_energy(self.heating_forecast)
                # self.evaluate_strategy()
            await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)

    def stop(self) -> None:
        self._stop_requested = True
        
    async def join(self):
        ...

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        from_node = self.layout.node(message.Header.Src)
        if not from_node:
            return Ok(True) # or not?
        match message.Payload:
            case ScadaParams():
                self.log("Received new parameters, time to recompute forecasts!")
                self.received_new_params = True
            case SyncedReadings():
                self.process_synced_readings(from_node, message.Payload)
        return Ok(True)

    def process_synced_readings(self, from_node: ShNode, payload: SyncedReadings) -> None:
        if from_node.name == H0N.buffer.reader:
            calibration = self.tmap.Buffer
            tank= H0CN.buffer
        else:
            tank_index = self.layout.h0n.tank_index(from_node.name)
            if tank_index is None:
                self.send_info(f"derived-generator got SyncedReadings from {from_node.name}"
                               " and only expects from tanks!")
                return
            calibration = self.tmap.Tank[tank_index]
            tank = self.h0cn.tank[tank_index]

        channel_names = []
        values = []
        for device_ch, raw_value,  in zip(payload.ChannelNameList, payload.ValueList):
            if device_ch not in tank.devices:
                continue # i.e. don't process micro-volts
            ch = tank.device_to_effective(device_ch)
            device_temp_f = self.to_fahrenheit(raw_value / 1000)
            depth = tank.device_depth(device_ch)
            m, b = self._depth_calibration(calibration, depth)

            # Use linear approximation from TankTempCalibrationMap
            temp_f =  m * device_temp_f + b
            # self.log(f"Got {round(device_temp_f,1)} F for {device_ch}")
            # self.log(f"{ch}: {round(temp_f, 1)}  = {m} * {round(device_temp_f,1)} + {b} ")

            # Derived tank temp channels have gw1.unit FahrenheitX100
            channel_names.append(ch)
            values.append(int(temp_f * 100))

        msg = SyncedReadings(
            ChannelNameList=channel_names,
            ValueList=values, # in FahrenheitX100
            ScadaReadTimeUnixMs=payload.ScadaReadTimeUnixMs
        )
        self._send_to(self.primary_scada, msg)

    def _depth_calibration(
        self,
        calibration: TankTempCalibration,
        depth: int,
    ) -> tuple[float, float]:
        if depth == 1:
            return calibration.Depth1M, calibration.Depth1B
        if depth == 2:
            return calibration.Depth2M, calibration.Depth2B
        if depth == 3:
            return calibration.Depth3M, calibration.Depth3B
        raise ValueError(f"Unsupported depth {depth}")

    # Compute usable and required energy
    def update_usable_energy(self) -> None:
        """
        Computes and publishes usable thermal energy (kWh) currently stored
        above the forecast-constrained return-water temperature.

        This method:
        - Simulates layer-by-layer discharge of tanks or buffer
        - Assumes stratified storage
        - Publishes usable energy as a SCADA reading
        """
        if self.layout.ha_strategy == HomeAloneStrategy.Summer:
            return

        if self.heating_forecast is None:
            self.log("Skipping energy update: heating_forecast not yet available")
            return

        latest_temps_f = self.latest_temps_f.copy()

        ordered_tank_layers = []
        if self.layout.ha_strategy == HomeAloneStrategy.WinterTou:
            for tank_idx in sorted(self.h0cn.tank):
                tank = self.h0cn.tank[tank_idx]
                ordered_tank_layers.extend([
                    tank.depth1,
                    tank.depth2,
                    tank.depth3,
                ])
        elif self.layout.ha_strategy == HomeAloneStrategy.ShoulderTou: 
            ordered_tank_layers = [
                    H0CN.buffer.depth1,
                    H0CN.buffer.depth2,
                    H0CN.buffer.depth3,
                ]
        else:
            raise ValueError(f"Unsupported HA strategy {self.layout.ha_strategy}")

        simulated_layers_f = [
            latest_temps_f[ch]
            for ch in ordered_tank_layers
            if ch in latest_temps_f
        ]

        if not simulated_layers_f:
            self.log("Usable energy not updated: no buffer/tank temperatures yet")
            return

        gallons_per_layer = (
            self.GALLONS_PER_TANK * len(self.h0cn.tank)
        ) / len(simulated_layers_f)

        mass_kg_per_layer = gallons_per_layer * self.GALLON_PER_LITER

        usable_kwh = 0
        while True:
            hottest_f = simulated_layers_f[0]
            rwt_f =self.rwt_f(hottest_f)

            if rwt_f is None:
                return
            if round(hottest_f) == round(rwt_f):
                simulated_layers_f = [
                    sum(simulated_layers_f) / len(simulated_layers_f)
                ] * len(simulated_layers_f)

                if round(simulated_layers_f[0]) == round(rwt_f):
                    break

            delta_c = (hottest_f - rwt_f) * 5 / 9

            # add this layer's delta energy
            usable_kwh += (
                mass_kg_per_layer
                * self.WATER_SPECIFIC_HEAT_KJ_PER_KG_C # kJoules needed to raise 1 liter 1 deg C
                * delta_c
                / 3600
            )
            # pop the layer
            simulated_layers_f = (
                simulated_layers_f[1:] + [rwt_f]
            )

        # self.log(f"Usable energy: {round(usable_kwh,1)} kWh")

        self._send_to(
                self.primary_scada,
                SingleReading(
                    ChannelName = H0CN.usable_energy,
                    Value=int(usable_kwh*1000),
                    ScadaReadTimeUnixMs=int(time.time() * 1000),
                ),
            )

    def evaluate_strategy(self):
        """
        Send an info Glitch if we think its time to change strategy
        """
        if self.layout.ha_strategy != HomeAloneStrategy.ShoulderTou:
            return
        if time.time() - self.last_evaluated_strategy > 3600:
            self.last_evaluated_strategy = time.time()
        else:
            return
        simulated_layers = [self.params.MaxEwtF]*3   
        max_buffer_usable_kwh = 0
        while True:
            if round(self.rwt_f(simulated_layers[0])) == round(simulated_layers[0]):
                simulated_layers = [sum(simulated_layers)/len(simulated_layers) for x in simulated_layers]
                if round(self.rwt_f(simulated_layers[0])) == round(simulated_layers[0]):
                    break
            max_buffer_usable_kwh += 120/3 * 3.78541 * 4.187/3600 * (simulated_layers[0]-self.rwt_f(simulated_layers[0]))*5/9
            simulated_layers = simulated_layers[1:] + [self.rwt_f(simulated_layers[0])]          
        self.log(f"Max buffer usable energy: {round(max_buffer_usable_kwh,1)} kWh")
        required_energy = self.data.latest_channel_values.get(H0CN.required_energy, 0)
        if round(max_buffer_usable_kwh,1) < round(required_energy,1):
            summary = "Consider changing strategy to use all tanks and not just the buffer"
            details = f"A full buffer will not have enough energy to go through the next on-peak ({round(max_buffer_usable_kwh,1)}<{round(self.required_kwh,1)} kWh)"
            self.log(details)
            self.send_info(summary, details)
        
    def update_required_energy(self, heating_forecast: HeatingForecast) -> None:
        """
        Computes and publishes the required thermal energy (kWh) needed to
        cover upcoming on-peak periods, based on forecasted load and
        maximum usable storage.

        This method:
        - Requires forecasts to be present
        - Does not store state locally
        - Publishes required energy as a SCADA reading

        If forecasts are unavailable, no update is sent.
        """
        required_kwh = 0
        time_now = datetime.now(self.timezone)
        if heating_forecast is None:
            self.log("Not updating required energy until forecasts exist")
            return

        forecasts_times_tz = [datetime.fromtimestamp(x, tz=self.timezone) for x in heating_forecast.Time]
        morning_kWh = sum(
            [kwh for t, kwh in zip(forecasts_times_tz, heating_forecast.AvgPowerKw)
             if 7<=t.hour<=11]
            )
        midday_kWh = sum(
            [kwh for t, kwh in zip(forecasts_times_tz, heating_forecast.AvgPowerKw)
             if 12<=t.hour<=15]
            )
        afternoon_kWh = sum(
            [kwh for t, kwh in zip(forecasts_times_tz, heating_forecast.AvgPowerKw)
             if 16<=t.hour<=19]
            )
        # Find the maximum storage
        if self.layout.ha_strategy == HomeAloneStrategy.WinterTou:
            num_layers = len(self.h0cn.tank) * self.NUM_LAYERS_PER_TANK
        elif self.layout.ha_strategy == HomeAloneStrategy.ShoulderTou:
            num_layers = self.NUM_LAYERS_PER_TANK # just the buffer
        else:
            raise Exception(f"not prepared for home alone strategy {self.layout.ha_strategy}")

        simulated_layers = [self.params.MaxEwtF + 10] * num_layers
        max_storage_kwh = 0
        while True:
            if round(self.rwt_f(simulated_layers[0])) == round(simulated_layers[0]):
                simulated_layers = [sum(simulated_layers)/len(simulated_layers) for x in simulated_layers]
                if round(self.rwt_f(simulated_layers[0])) == round(simulated_layers[0]):
                    break

            max_storage_kwh += 120/3 * 3.78541 * 4.187/3600 * (simulated_layers[0]-self.rwt_f(simulated_layers[0]))*5/9
            simulated_layers = simulated_layers[1:] + [self.rwt_f(simulated_layers[0])]
        if (((time_now.weekday()<4 or time_now.weekday()==6) and time_now.hour>=20) or (time_now.weekday()<5 and time_now.hour<=6)):
            self.log('Preparing for a morning onpeak + afternoon onpeak')
            afternoon_missing_kWh = afternoon_kWh - (4*self.params.HpMaxKwTh - midday_kWh) # TODO make the kW_th a function of COP and kW_el
            if afternoon_missing_kWh<0:
                required = morning_kWh
            else:
                required = morning_kWh + afternoon_missing_kWh
            required_kwh = min(required, max_storage_kwh)
        elif (time_now.weekday()<5 and time_now.hour>=12 and time_now.hour<16):
            self.log('Preparing for an afternoon onpeak')
            required_kwh = afternoon_kWh
        else:
            self.log("Currently in on-peak or no on-peak period coming up soon")
            
        # self.log(f"Required energy: {round(required_kwh,1)} kWh")
        self._send_to(
                self.primary_scada,
                SingleReading(
                    ChannelName=H0CN.required_energy,
                    Value=int(required_kwh*1000),
                    ScadaReadTimeUnixMs=int(time.time() * 1000),
                ),
            )

    def delta_T(self, swt: float) -> float:
        a, b, c = self.rswt_quadratic_params
        delivered_heat_power = a*swt**2 + b*swt + c
        dd_delta_t = self.params.DdDeltaTF
        dd_power = self.params.DdPowerKw
        d = dd_delta_t/dd_power * delivered_heat_power
        return d if d>0 else 0
        
    def required_heating_power(self, oat: float, wind_speed_mph: float) -> float:
        ws = wind_speed_mph
        alpha = self.params.AlphaTimes10 / 10
        beta = self.params.BetaTimes100 / 100
        gamma = self.params.GammaEx6 / 1e6
        r = alpha + beta*oat + gamma*ws
        r = r * (1 + self.settings.load_overestimation_percent/100)
        return round(r,2) if r>0 else 0

    def required_swt(self, required_kw_thermal: float) -> float:
        a, b, c = self.rswt_quadratic_params
        c2 = c - required_kw_thermal
        return round((-b + (b**2-4*a*c2)**0.5)/(2*a), 2)
    
    async def get_weather(self, session: aiohttp.ClientSession) -> None:
        config_dir = self.settings.paths.config_dir
        weather_file = config_dir / "weather.json"
        try:
            url = f"https://api.weather.gov/points/{self.latitude},{self.longitude}"
            response = await session.get(url)
            if response.status != 200:
                self.log(f"Error fetching weather forecast url: {response.status}")
                raise Exception()
            
            data = await response.json()
            forecast_hourly_url = data['properties']['forecastHourly']
            forecast_response = await session.get(forecast_hourly_url)
            if forecast_response.status != 200:
                self.log(f"Error fetching hourly weather forecast: {forecast_response.status}")
                raise Exception()
            
            forecast_data = await forecast_response.json()
            forecasts_all = {
                datetime.fromisoformat(period['startTime']): 
                period['temperature']
                for period in forecast_data['properties']['periods']
                if 'temperature' in period and 'startTime' in period 
                and datetime.fromisoformat(period['startTime']) > datetime.now(tz=self.timezone)
            }
            ws_forecasts_all = {
                datetime.fromisoformat(period['startTime']): 
                int(period['windSpeed'].replace(' mph',''))
                for period in forecast_data['properties']['periods']
                if 'windSpeed' in period and 'startTime' in period 
                and datetime.fromisoformat(period['startTime']) > datetime.now(tz=self.timezone)
            }
            forecasts_48h = dict(list(forecasts_all.items())[:48])
            ws_forecasts_48h = dict(list(ws_forecasts_all.items())[:48])
            weather = {
                'time': [int(x.astimezone(timezone.utc).timestamp()) for x in list(forecasts_48h.keys())],
                'oat': list(forecasts_48h.values()),
                'ws': list(ws_forecasts_48h.values())
                }
            self.log(f"Obtained a {len(forecasts_all)}-hour weather forecast starting at {weather['time'][0]}")

            # Save 96h weather forecast to a local file
            forecasts_96h = dict(list(forecasts_all.items())[:96])
            ws_forecasts_96h = dict(list(ws_forecasts_all.items())[:96])
            weather_96h = {
                'time': [int(x.astimezone(timezone.utc).timestamp()) for x in list(forecasts_96h.keys())],
                'oat': list(forecasts_96h.values()),
                'ws': list(ws_forecasts_96h.values()),
                }
            with open(weather_file, 'w') as f:
                json.dump(weather_96h, f, indent=4) 
        
        except Exception as e:
            self.log(f"[!] Unable to get weather forecast from API: {e}")
            try:
                # Try reading an old forecast from local file
                with open(weather_file, 'r') as f:
                    weather_96h = json.load(f)
                    self.weather_96h = weather_96h
                if weather_96h['time'][-1] >= time.time()+ 48*3600:
                    self.log("A valid weather forecast is available locally.")
                    seconds_late = time.time() - weather_96h['time'][0]
                    hours_late = math.ceil(seconds_late/3600)
                    weather = {}
                    for key in weather_96h:
                        weather[key] = weather_96h[key][hours_late:hours_late+48]
                    self.first_time = weather['time'][0]
                    if weather['oat'] == []:
                        raise Exception()
                    if weather['time'][0] < time.time():
                        raise Exception(f"Weather forecast start of {weather['time'][0]} is in the past!! Check math")
                else:
                    self.log("No valid weather forecasts available locally. Using coldest of the current month.")
                    current_month = datetime.now().month-1
                    weather = {
                        'time': [int(time.time()+(1+x)*3600) for x in range(48)],
                        'oat': [self.coldest_oat_by_month[current_month]]*48,
                        'ws': [0]*48,
                        }
            except Exception as e:
                self.log(f"Issue getting local weather forecast! Using coldest of the current month.\n Issue: {e}")
                current_month = datetime.now().month-1
                weather = {
                    'time': [int(time.time()+(1+x)*3600) for x in range(48)],
                    'oat': [self.coldest_oat_by_month[current_month]]*48,
                    'ws': [0]*48,
                    }
        # International Civil Aviation Organization: 4-char alphanumeric code
        # assigned to airports and weather observation stations
        ICAO_CODE = "KMLT"
        WEATHER_CHANNEL = f"weather.gov.{ICAO_CODE}".lower()

        self.weather_forecast = WeatherForecast(
            FromGNodeAlias=self.layout.scada_g_node_alias,
            WeatherChannelName=WEATHER_CHANNEL,
            Time = weather['time'],
            OatF = weather['oat'],
            WindSpeedMph= weather['ws'],
        )

    async def get_forecasts(self, session: aiohttp.ClientSession):
    
        await self.get_weather(session)
        if self.weather_forecast is None:
            self.log("No weather forecast available. Could not compute heating forecasts.")
            return
        
        forecasts = {}
        forecasts['time'] = self.weather_forecast.Time
        forecasts['avg_power'] = [
            self.required_heating_power(oat, ws) 
            for oat, ws in zip(self.weather_forecast.OatF, self.weather_forecast.WindSpeedMph)]
        forecasts['required_swt'] = [self.required_swt(x) for x in forecasts['avg_power']]
        forecasts['required_swt_delta_T'] = [round(self.delta_T(x),2) for x in forecasts['required_swt']]

        # Send cropped 24-hour heating forecast to aa & ha for their own use
        # and send both the 48-hour weather forecast and 24-hr heating forecast to atn for record-keeping
        hf = HeatingForecast(
            FromGNodeAlias=self.layout.scada_g_node_alias,
            Time = forecasts['time'][:24],
            AvgPowerKw = forecasts['avg_power'][:24],
            RswtF = forecasts['required_swt'][:24],
            RswtDeltaTF = forecasts['required_swt_delta_T'][:24],
            WeatherUid=self.weather_forecast.WeatherUid
        )

        # Ensure energy state is up-to-date before publishing forecast;
        # downstream actors treat the forecast as a trigger, not as state.
        self.data.heating_forecast = hf
        self._send_to(self.atn, hf)
        self._send_to(self.atn, self.weather_forecast)

        if not self.first_required_energy_update_done:
            self.log("Updating usable and required energy")
            self.update_usable_energy()
            self.update_required_energy(hf)
            self.first_required_energy_update_done = True

        forecast_start = datetime.fromtimestamp(self.weather_forecast.Time[0], tz=self.timezone)
        self.log(f"Got forecast starting {forecast_start.strftime('%Y-%m-%d %H:%M:%S')}")

    def rwt_f(self, swt_f: float) -> float:
        """
        Returns the forecast-constrained return water temperature for a given
        source (leaving) water temperature.

        This function models how much heat can be extracted from water at temperature
        `swt_f` while attempting to meet the forecasted load:

        - If `swt_f` is well below the required SWT, no heat can be extracted
        and return temperature equals supply temperature.
        - If `swt_f` is near the required SWT, partial extraction is possible
        with a reduced delta-T.
        - If `swt_f` is above the required SWT, full extraction is assumed.

        NOTE:
        This is not "the return water temperature at required SWT".
        It is a load- and forecast-limited effective return temperature.
        Requires self.heating_forecast
        """
        if self.heating_forecast is None:
            raise RuntimeError(
                "rwt_f called before heating_forecast is available"
            )
        forecasts_times_tz = [datetime.fromtimestamp(x, tz=self.timezone) for x in self.heating_forecast.Time]
        timenow = datetime.now(self.timezone)
        if timenow.hour > 19 or timenow.hour < 12:
            required_swt = max(
                [rswt for t, rswt in zip(forecasts_times_tz, self.heating_forecast.RswtF)
                if t.hour in [7,8,9,10,11,16,17,18,19]]
                )
        else:
            required_swt = max(
                [rswt for t, rswt in zip(forecasts_times_tz, self.heating_forecast.RswtF)
                if t.hour in [16,17,18,19]]
                )
        if swt_f < required_swt - 10:
            delta_t = 0
        elif swt_f < required_swt:
            delta_t = self.delta_T(required_swt) * (swt_f-(required_swt-10))/10
        else:
            delta_t = self.delta_T(swt_f)
        return round(swt_f - delta_t,2)
