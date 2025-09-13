import numpy as np
from typing import Optional
from gwsproto.named_types import FloParamsHouse0


class DParams():
    def __init__(self, flo_params: FloParamsHouse0) -> None:
        self.flo_params = flo_params
        self.start_time = flo_params.StartUnixS
        self.horizon = flo_params.HorizonHours
        self.num_layers = flo_params.NumLayers
        self.storage_volume = flo_params.StorageVolumeGallons
        self.max_hp_elec_in = flo_params.HpMaxElecKw
        self.min_hp_elec_in = flo_params.HpMinElecKw
        self.initial_top_temp = flo_params.InitialTopTempF
        self.initial_middle_temp = flo_params.InitialMiddleTempF
        self.initial_bottom_temp = flo_params.InitialBottomTempF
        self.initial_thermocline1 = flo_params.InitialThermocline1
        self.initial_thermocline2 = flo_params.InitialThermocline2
        self.storage_losses_percent = flo_params.StorageLossesPercent
        self.reg_forecast = [x/10 for x in flo_params.RegPriceForecast[:self.horizon]]
        self.dist_forecast = [x/10 for x in flo_params.DistPriceForecast[:self.horizon]]
        self.lmp_forecast = [x/10 for x in flo_params.LmpForecast[:self.horizon]]
        self.elec_price_forecast = [rp+dp+lmp for rp,dp,lmp in zip(self.reg_forecast, self.dist_forecast, self.lmp_forecast)]
        self.oat_forecast = flo_params.OatForecastF[:self.horizon]
        self.ws_forecast = flo_params.WindSpeedForecastMph[:self.horizon]
        self.alpha = flo_params.AlphaTimes10/10
        self.beta = flo_params.BetaTimes100/100
        self.gamma = flo_params.GammaEx6/1e6
        self.no_power_rswt = -self.alpha/self.beta
        self.intermediate_power = flo_params.IntermediatePowerKw
        self.intermediate_rswt = flo_params.IntermediateRswtF
        self.dd_power = flo_params.DdPowerKw
        self.dd_rswt = flo_params.DdRswtF
        self.dd_delta_t = flo_params.DdDeltaTF
        self.hp_is_off = flo_params.HpIsOff
        self.hp_turn_on_minutes = flo_params.HpTurnOnMinutes
        self.quadratic_coefficients = self.get_quadratic_coeffs()
        self.load_forecast = [self.required_heating_power(oat,ws) for oat,ws in zip(self.oat_forecast,self.ws_forecast)]
        self.rswt_forecast = [self.required_swt(x) for x in self.load_forecast]

        # Edit load forecast to include energy available in the buffer
        available_buffer = flo_params.BufferAvailableKwh
        i = 0
        while available_buffer > 0 and i < len(self.load_forecast):
            load_backup = self.load_forecast[i]
            self.load_forecast[i] = self.load_forecast[i] - min(available_buffer, self.load_forecast[i])
            available_buffer = available_buffer - min(available_buffer, load_backup)
            i += 1

        # Edit load forecast to include energy available in the house (zones above thermostat)
        available_house = flo_params.HouseAvailableKwh
        i = 0
        if available_house < 0:
            self.load_forecast[0] += -available_house
        else:
            while available_house > 0 and i < len(self.load_forecast):
                load_backup = self.load_forecast[i]
                self.load_forecast[i] = self.load_forecast[i] - min(available_house, self.load_forecast[i])
                available_house = available_house - min(available_house, load_backup)
                i += 1
        
        # Check HP sizing and cap load
        self.load_forecast = [round(x,2) for x in self.load_forecast]
        max_load_elec = max(self.load_forecast) / self.COP(min(self.oat_forecast), max(self.rswt_forecast))
        if max_load_elec > self.max_hp_elec_in:
            print(
                f"WARNING! The HP is undersized for the given load forecast "
                f"(need {round(max_load_elec,2)} kWh_e but can only reach {self.max_hp_elec_in} kWh_e)."
            )
            max_hp_elec_in = [self.max_hp_elec_in for _ in self.oat_forecast]
            for h in range(len(max_hp_elec_in)):
                turn_on_minutes = self.hp_turn_on_minutes if h==0 else self.hp_turn_on_minutes/2
                max_hp_elec_in[h] = ((1-turn_on_minutes/60) if (h==0 and self.hp_is_off) else 1) * self.max_hp_elec_in
            all_max_hp = [round(power*self.COP(oat),2) for power, oat in zip(max_hp_elec_in, self.oat_forecast)]
            self.load_forecast = [min(max_hp, self.load_forecast[i]) for i, max_hp in enumerate(all_max_hp)]
            print("The load forecast has been capped to the HP's maximum power output.\n")
    
    def COP(self, oat, lwt=None):
        if oat < self.flo_params.CopMinOatF: 
            return self.flo_params.CopMin
        else:
            return self.flo_params.CopIntercept + self.flo_params.CopOatCoeff * oat

    def required_heating_power(self, oat, ws):
        r = self.alpha + self.beta*oat + self.gamma*ws
        return r if r>0 else 0

    def delivered_heating_power(self, swt):
        a, b, c = self.quadratic_coefficients
        d = a*swt**2 + b*swt + c
        return d if d>0 else 0

    def required_swt(self, rhp):
        a, b, c = self.quadratic_coefficients
        c2 = c - rhp
        return (-b + (b**2-4*a*c2)**0.5)/(2*a)

    def delta_T(self, swt):
        return 20
    
    def delta_T_inverse(self, rwt: float) -> float:
        a, b, c = self.quadratic_coefficients
        aa = -self.dd_delta_t/self.dd_power * a
        bb = 1-self.dd_delta_t/self.dd_power * b
        cc = -self.dd_delta_t/self.dd_power * c - rwt
        if bb**2-4*aa*cc < 0 or (-bb + (bb**2-4*aa*cc)**0.5)/(2*aa) - rwt > 30:
            return 30
        return (-bb + (bb**2-4*aa*cc)**0.5)/(2*aa) - rwt
    
    def get_quadratic_coeffs(self):
        x_rswt = np.array([self.no_power_rswt, self.intermediate_rswt, self.dd_rswt])
        y_hpower = np.array([0, self.intermediate_power, self.dd_power])
        A = np.vstack([x_rswt**2, x_rswt, np.ones_like(x_rswt)]).T
        return [float(x) for x in np.linalg.solve(A, y_hpower)] 


class DNode():
    def __init__(
            self, 
            parameters: DParams,
            top_temp: float, 
            middle_temp: float,
            bottom_temp: float, 
            thermocline1: int, 
            thermocline2: int, 
            time_slice: Optional[int]=0
            ):
        self.params = parameters
        self.time_slice = time_slice
        # State
        self.top_temp = top_temp
        self.middle_temp = middle_temp
        self.bottom_temp = bottom_temp
        self.thermocline1 = thermocline1
        self.thermocline2 = thermocline2
        self.energy = self.get_energy()
        # Dijkstra's algorithm
        self.pathcost = 0 if time_slice==self.params.horizon else 1e9
        self.next_node = None        

    def to_string(self):
        return f"{self.top_temp}({self.thermocline1}){self.middle_temp}({self.thermocline2}){self.bottom_temp}"

    def __repr__(self):
        return f"[{self.time_slice}]{self.top_temp}({self.thermocline1}){self.middle_temp}({self.thermocline2}){self.bottom_temp}"
        
    def get_energy(self):
        m_layer_kg = self.params.storage_volume*3.785 / self.params.num_layers
        kWh_top = self.thermocline1*m_layer_kg * 4.187/3600 * to_kelvin(self.top_temp)
        kWh_midlle = (self.thermocline2-self.thermocline1)*m_layer_kg * 4.187/3600 * to_kelvin(self.middle_temp)
        kWh_bottom = (self.params.num_layers-self.thermocline2)*m_layer_kg * 4.187/3600 * to_kelvin(self.bottom_temp)
        return kWh_top + kWh_midlle + kWh_bottom


class DEdge():
    def __init__(self, tail:DNode, head:DNode, cost:float, hp_heat_out:float):
        self.tail: DNode = tail
        self.head: DNode = head
        self.cost = cost
        self.hp_heat_out = hp_heat_out

    def __repr__(self):
        return f"Edge[{self.tail} --cost:{round(self.cost,3)}, hp:{round(self.hp_heat_out,2)}--> {self.head}]"
    

def to_kelvin(t):
    return (t-32)*5/9 + 273.15