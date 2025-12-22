import time
import json
import pytz
import asyncio
import aiohttp
import math
import numpy as np
from typing import Optional, Sequence, cast
from result import Ok, Result
from datetime import datetime,  timezone
from gwproto import Message
from gwproto.data_classes.sh_node import ShNode
from gwproto.named_types import SyncedReadings
from gwproto.named_types import SingleReading, PicoTankModuleComponentGt
from gwsproto.named_types import Glitch
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage

from actors.scada_actor import ScadaActor
from gwsproto.enums import HomeAloneStrategy, LogLevel
from gwsproto.data_classes.house_0_names import H0CN, H0N
from gwsproto.named_types import (Ha1Params, HeatingForecast,
                         WeatherForecast, ScadaParams)
from scada_app_interface import ScadaAppInterface


class SynthGenerator(ScadaActor):
    MAIN_LOOP_SLEEP_SECONDS = 60

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self._stop_requested: bool = False
        self.hardware_layout = self._services.hardware_layout

        self.buffer_depths_unadjusted = self.h0cn.buffer_unadjusted.all
        self.tank_depths_unadjusted = [depth for i in self.h0cn.tank_unadjusted for depth in self.h0cn.tank_unadjusted[i].all]
        buffer_depths = self.h0cn.buffer.all
        tank_depths = [depth for i in self.h0cn.tank for depth in self.h0cn.tank[i].all]
        self.temperature_channel_names = buffer_depths + tank_depths + [
            self.h0cn.hp_ewt, self.h0cn.hp_lwt, self.h0cn.dist_swt, self.h0cn.dist_rwt, 
            self.h0cn.buffer_cold_pipe, self.h0cn.buffer_hot_pipe, self.h0cn.store_cold_pipe, self.h0cn.store_hot_pipe,
        ]
        self.elec_assigned_amount = None
        self.previous_time = None
        self.temperatures_available = False
        self.received_new_params: bool = False
        self.last_evaluated_strategy = 0

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

        self.forecasts: Optional[HeatingForecast]= None
        self.weather_forecast: Optional[WeatherForecast] = None
        self.coldest_oat_by_month = [-3, -7, 1, 21, 30, 31, 46, 47, 28, 24, 16, 0]
    
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
        await self.get_forecasts(session)
        await asyncio.sleep(2)
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))

            if self.forecasts is None or time.time()>self.forecasts.Time[0] or self.received_new_params:
                await self.get_forecasts(session)
                self.received_new_params = False

            self.get_latest_temperatures()
            if self.temperatures_available:
                self.update_energy()
            await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)

    def stop(self) -> None:
        self._stop_requested = True
        
    async def join(self):
        ...

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        match message.Payload:
            case ScadaParams():
                self.log("Received new parameters, time to recompute forecasts!")
                self.received_new_params = True
            case SyncedReadings():
                try:
                    self.process_synced_readings(message.Header.Src, message.Payload)
                    self._temp_adjustment_failed = False
                except Exception as e:
                    self.log(f"Temp adjustment failed: {e}")

                    if not self._temp_adjustment_failed:
                        self._temp_adjustment_failed = True
                        self._send_to(
                            self.atn,
                            Glitch(
                                FromGNodeAlias=self.layout.scada_g_node_alias,
                                Node=self.node.Name,
                                Type=LogLevel.Warning,
                                Summary="Tank temperature adjustment failed",
                                Details=str(e),
                            )
                        )
        return Ok(True)

    def process_synced_readings(self, actor: ShNode, payload: SyncedReadings) -> None:
        """
        Uses the unadjusted tank temperature data to create the temp data we will use.
        """
        self.log(f"Received a SyncReadings message from {actor.Name} with {len(payload.ChannelNameList)} channels")
        channel_name_list = []
        value_list = []
        for i, channel_name in enumerate(payload.ChannelNameList):
            if channel_name in self.buffer_depths_unadjusted + self.tank_depths_unadjusted:
                channel_name_list.append(channel_name.replace('-unadjusted', ''))
                value_list.append(payload.ValueList[i])
                print(f"Done adjusting channel {channel_name}")
        
        self._send_to(
            self.primary_scada, 
            SyncedReadings(
                ChannelNameList=channel_name_list,
                ValueList=value_list,
                ScadaReadTimeUnixMs=int(time.time() * 1000),
            )
        )
    
    def fill_missing_store_temps(self):
        all_store_layers = sorted([x for x in self.temperature_channel_names if 'tank' in x])
        for layer in all_store_layers:
            if (layer not in self.latest_temperatures 
            or self.to_fahrenheit(self.latest_temperatures[layer]/1000) < 70
            or self.to_fahrenheit(self.latest_temperatures[layer]/1000) > 200):
                self.latest_temperatures[layer] = None
        if H0CN.store_cold_pipe in self.latest_temperatures:
            value_below = self.latest_temperatures[H0CN.store_cold_pipe]
        else:
            value_below = 0
        for layer in sorted(all_store_layers, reverse=True):
            if self.latest_temperatures[layer] is None:
                self.latest_temperatures[layer] = value_below
            value_below = self.latest_temperatures[layer]  
        self.latest_temperatures = {k:self.latest_temperatures[k] for k in sorted(self.latest_temperatures)}
    
    # Receive latest temperatures
    def get_latest_temperatures(self):
        if not self.is_simulated:
            temp = {
                x: self.data.latest_channel_values[x] 
                for x in self.temperature_channel_names
                if x in self.data.latest_channel_values
                and self.data.latest_channel_values[x] is not None
                }
            self.latest_temperatures = temp.copy()
        else:
            self.log("IN SIMULATION - set all temperatures to 60 degC")
            self.latest_temperatures = {}
            for channel_name in self.temperature_channel_names:
                self.latest_temperatures[channel_name] = 60 * 1000
        if list(self.latest_temperatures.keys()) == self.temperature_channel_names:
            self.temperatures_available = True
        else:
            self.temperatures_available = False
            all_buffer = [x for x in self.temperature_channel_names if 'buffer-depth' in x]
            available_buffer = [x for x in list(self.latest_temperatures.keys()) if 'buffer-depth' in x]
            if all_buffer == available_buffer:
                if self.layout.ha_strategy != HomeAloneStrategy.ShoulderTou:
                    self.fill_missing_store_temps()
                self.temperatures_available = True


    # Compute usable and required energy
    def update_energy(self) -> None:
        
        time_now = datetime.now(self.timezone)
        latest_temperatures = self.latest_temperatures.copy()

        if self.layout.ha_strategy in [HomeAloneStrategy.Summer]:
            #self.log(f"Does not calculate usable/required energy in {self.layout.ha_strategy} ")
            return

        if self.layout.ha_strategy == HomeAloneStrategy.WinterTou:
            storage_temperatures = {k:v for k,v in latest_temperatures.items() if 'tank' in k}
            simulated_layers = [self.to_fahrenheit(v/1000) for k,v in storage_temperatures.items()]
        elif self.layout.ha_strategy == HomeAloneStrategy.ShoulderTou: 
            buffer_temperatures = {k:v for k,v in latest_temperatures.items() if 'buffer' in k and 'depth' in k}
            simulated_layers = [self.to_fahrenheit(v/1000) for k,v in buffer_temperatures.items()]   
        else:
            raise Exception(f"not prepared for home alone strategy {self.layout.ha_strategy}")    
        self.usable_kwh = 0
        while True:
            if round(self.rwt(simulated_layers[0])) == round(simulated_layers[0]):
                simulated_layers = [sum(simulated_layers)/len(simulated_layers) for x in simulated_layers]
                if round(self.rwt(simulated_layers[0])) == round(simulated_layers[0]):
                    break
            self.usable_kwh += 120/3 * 3.78541 * 4.187/3600 * (simulated_layers[0]-self.rwt(simulated_layers[0]))*5/9
            self.usable_kwh = max(0, self.usable_kwh)
            simulated_layers = simulated_layers[1:] + [self.rwt(simulated_layers[0])]          
        self.required_kwh = self.get_required_storage(time_now)
        self.log(f"Usable energy: {round(self.usable_kwh,1)} kWh")
        self.log(f"Required energy: {round(self.required_kwh,1)} kWh")
        self.evaluate_strategy()

        # Post usable and required energy
        t_ms = int(time.time() * 1000)
        self._send_to(
                self.primary_scada,
                SingleReading(
                    ChannelName="usable-energy",
                    Value=int(self.usable_kwh*1000),
                    ScadaReadTimeUnixMs=t_ms,
                ),
            )
        self._send_to(
                self.primary_scada,
                SingleReading(
                    ChannelName="required-energy",
                    Value=int(self.required_kwh*1000),
                    ScadaReadTimeUnixMs=t_ms,
                ),
            )
        
    def evaluate_strategy(self):
        if self.layout.ha_strategy != HomeAloneStrategy.ShoulderTou:
            return
        if time.time() - self.last_evaluated_strategy > 3600:
            self.last_evaluated_strategy = time.time()
        else:
            return
        simulated_layers = [self.params.MaxEwtF]*3   
        max_buffer_usable_kwh = 0
        while True:
            if round(self.rwt(simulated_layers[0])) == round(simulated_layers[0]):
                simulated_layers = [sum(simulated_layers)/len(simulated_layers) for x in simulated_layers]
                if round(self.rwt(simulated_layers[0])) == round(simulated_layers[0]):
                    break
            max_buffer_usable_kwh += 120/3 * 3.78541 * 4.187/3600 * (simulated_layers[0]-self.rwt(simulated_layers[0]))*5/9
            simulated_layers = simulated_layers[1:] + [self.rwt(simulated_layers[0])]          
        self.log(f"Max buffer usable energy: {round(max_buffer_usable_kwh,1)} kWh")
        if round(max_buffer_usable_kwh,1) < round(self.required_kwh,1):
            summary = "Consider changing strategy to use all tanks and not just the buffer"
            details = f"A full buffer will not have enough energy to go through the next on-peak ({round(max_buffer_usable_kwh,1)}<{round(self.required_kwh,1)} kWh)"
            self.log(details)
            self.send_info(summary, details)
        
    def get_required_storage(self, time_now: datetime) -> float:
        forecasts_times_tz = [datetime.fromtimestamp(x, tz=self.timezone) for x in self.forecasts.Time]
        morning_kWh = sum(
            [kwh for t, kwh in zip(forecasts_times_tz, self.forecasts.AvgPowerKw) 
             if 7<=t.hour<=11]
            )
        midday_kWh = sum(
            [kwh for t, kwh in zip(forecasts_times_tz, self.forecasts.AvgPowerKw)
             if 12<=t.hour<=15]
            )
        afternoon_kWh = sum(
            [kwh for t, kwh in zip(forecasts_times_tz, self.forecasts.AvgPowerKw)
             if 16<=t.hour<=19]
            )
        # Find the maximum storage
        if self.layout.ha_strategy == HomeAloneStrategy.WinterTou:
            simulated_layers = [self.params.MaxEwtF + 10] * 3 * 3
        elif self.layout.ha_strategy == HomeAloneStrategy.ShoulderTou:
            simulated_layers = [self.params.MaxEwtF + 10] * 3 * 1
        else:
            raise Exception(f"not prepared for home alone strategy {self.layout.ha_strategy}")
    
        max_storage_kwh = 0
        while True:
            if round(self.rwt(simulated_layers[0])) == round(simulated_layers[0]):
                simulated_layers = [sum(simulated_layers)/len(simulated_layers) for x in simulated_layers]
                if round(self.rwt(simulated_layers[0])) == round(simulated_layers[0]):
                    break
            max_storage_kwh += 120/3 * 3.78541 * 4.187/3600 * (simulated_layers[0]-self.rwt(simulated_layers[0]))*5/9
            simulated_layers = simulated_layers[1:] + [self.rwt(simulated_layers[0])]
        if (((time_now.weekday()<4 or time_now.weekday()==6) and time_now.hour>=20) or (time_now.weekday()<5 and time_now.hour<=6)):
            self.log('Preparing for a morning onpeak + afternoon onpeak')
            afternoon_missing_kWh = afternoon_kWh - (4*self.params.HpMaxKwTh - midday_kWh) # TODO make the kW_th a function of COP and kW_el
            if afternoon_missing_kWh<0:
                required = morning_kWh
            else:
                required = morning_kWh + afternoon_missing_kWh
            required_kwh = min(required, max_storage_kwh)
            return required_kwh
        elif (time_now.weekday()<5 and time_now.hour>=12 and time_now.hour<16):
            self.log('Preparing for an afternoon onpeak')
            return afternoon_kWh
        else:
            self.log('Currently in on-peak or no on-peak period coming up soon')
            return 0

    def to_celcius(self, t: float) -> float:
        return (t-32)*5/9

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

        # Send cropped 24-hour heating  forecast to aa & ha for their own use
        # and send both the 48-hour weather forecast and 24-hr heating forecast to atn for record-keeping
        hf = HeatingForecast(
            FromGNodeAlias=self.layout.scada_g_node_alias,
            Time = forecasts['time'][:24],
            AvgPowerKw = forecasts['avg_power'][:24],
            RswtF = forecasts['required_swt'][:24],
            RswtDeltaTF = forecasts['required_swt_delta_T'][:24],
            WeatherUid=self.weather_forecast.WeatherUid
        )
  
        self._send_to(self.home_alone, hf)
        self._send_to(self.atomic_ally, hf)
        self._send_to(self.atn, self.weather_forecast)
        self._send_to(self.atn, hf)
        self.forecasts = hf
        forecast_start = datetime.fromtimestamp(self.weather_forecast.Time[0], tz=self.timezone)
        self.log(f"Got forecast starting {forecast_start.strftime('%Y-%m-%d %H:%M:%S')}")


    def rwt(self, swt: float, return_rswt_onpeak=False) -> float:
        if self.forecasts is None:
            self.log("Forecasts are not available, can not find RWT")
            return
        forecasts_times_tz = [datetime.fromtimestamp(x, tz=self.timezone) for x in self.forecasts.Time]
        timenow = datetime.now(self.timezone)
        if timenow.hour > 19 or timenow.hour < 12:
            required_swt = max(
                [rswt for t, rswt in zip(forecasts_times_tz, self.forecasts.RswtF)
                if t.hour in [7,8,9,10,11,16,17,18,19]]
                )
        else:
            required_swt = max(
                [rswt for t, rswt in zip(forecasts_times_tz, self.forecasts.RswtF)
                if t.hour in [16,17,18,19]]
                )
        if return_rswt_onpeak:
            return required_swt
        if swt < required_swt - 10:
            delta_t = 0
        elif swt < required_swt:
            delta_t = self.delta_T(required_swt) * (swt-(required_swt-10))/10
        else:
            delta_t = self.delta_T(swt)
        return round(swt - delta_t,2)

    def send_glitch(self, summary: str, details: str, log_level: LogLevel = LogLevel.Info) -> None:
        msg = Glitch(
            FromGNodeAlias=self.layout.scada_g_node_alias,
            Node=self.node.Name,
            Type=log_level,
            Summary=summary,
            Details=details
        )
        self._send_to(self.atn, msg)
        self.log(f"Glitch: {summary}")