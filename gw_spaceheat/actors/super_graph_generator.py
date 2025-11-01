from typing import Dict, List, Tuple
import json
import time
from gwsproto.named_types import FloParamsHouse0
from dijkstra_types import DParams, DNode, to_kelvin


class SuperGraphGenerator():
    def __init__(self, flo_params: FloParamsHouse0):
        self.params = DParams(flo_params)

    def generate(self):
        start_time = time.time()
        self.create_nodes()
        self.create_edges()
        self.save_to_json()
        print(f"\nGenerating SuperGraph took {int(time.time()-start_time)} seconds.")

    def create_nodes(self):
        print("Creating nodes...")
        self.top_temps = sorted(list(range(110,170+10,10)), reverse=True)
        self.middle_temps = [x-10 for x in self.top_temps[:-1]] 
        self.bottom_temps = [100]

        thermocline_combinations = []
        for t1 in range(1,self.params.num_layers+1):
            for t2 in range(1,self.params.num_layers+1):
                if t2>=t1:
                    thermocline_combinations.append((t1,t2))
        print(f"=> {len(thermocline_combinations)} thermocline combinations")

        temperature_combinations = []
        for t in self.top_temps:
            for m in self.middle_temps:
                for b in self.bottom_temps:
                    if b<=m-10 and m<=t-10:
                        temperature_combinations.append((t,m,b))
        print(f"=> {len(temperature_combinations)} temperature combinations")

        temperature_combinations += [(110,100,100)]
        temperature_combinations += [(100,80,80), (80,60,60)]

        self.nodes: List[DNode] = []
        self.nodes_by: Dict[Tuple, Dict[Tuple, DNode]] = {
            tmb: {th: None for th in thermocline_combinations} for tmb in temperature_combinations
            }
                
        total_nodes=0
        for tmb in temperature_combinations:
            for th in thermocline_combinations:
                t, m, b = tmb
                th1, th2 = th
                if m==b and th1!=th2:
                    continue
                node = DNode(
                    top_temp=t,
                    middle_temp=m,
                    bottom_temp=b,
                    thermocline1=th1,
                    thermocline2=th2,
                    parameters=self.params
                    )
                self.nodes.append(node)
                self.nodes_by[tmb][th] = node
                total_nodes += 1     
        print(f"=> Created a total of {total_nodes} nodes")

    def create_edges(self):
        print("\nCreating edges...")
        max_hp_out = self.params.max_hp_elec_in * self.params.COP(oat=50)
        max_load = max_hp_out
        store_heat_in_range = [x/10 for x in range(-int(max_load*10), int(max_hp_out*10)+1)]
        print(
            f"The store can receive heat in the "
            f"[{store_heat_in_range[0]}, {store_heat_in_range[-1]}] kWh range, with a 0.1 kWh step."
            )
        
        allowed_temperatures = {
            'top': self.top_temps,
            'middle': self.middle_temps,
            'bottom': self.bottom_temps
        }
        storage_model = StorageModel(self.params.flo_params, self.nodes, self.nodes_by, allowed_temperatures)
        self.super_graph: Dict[str, Dict[str, str]] = {}

        for store_heat_in in store_heat_in_range:
            print(f"Generating edges for store_heat_in = {store_heat_in} kWh")
            self.super_graph[str(store_heat_in)] = {}
            for node in self.nodes:
                self.super_graph[str(store_heat_in)][node.to_string()] = (
                    storage_model.next_node(node, store_heat_in).to_string()
                )
        
    def save_to_json(self):
        print("\nSaving SuperGraph to JSON...")
        json_file_path = f"super_graph_{self.params.storage_volume}.json"
        with open(json_file_path, 'w') as f:
            json.dump(self.super_graph, f)
        print("Done.")


class StorageModel():
    def __init__(self, flo_params: FloParamsHouse0, nodes: List, nodes_by: Dict, allowed_temperatures: Dict):
        self.params = DParams(flo_params)
        self.nodes: List[DNode] = nodes
        self.nodes_by: Dict[Tuple, Dict[Tuple, DNode]] = nodes_by
        self.top_temps = allowed_temperatures['top']
        self.middle_temps = allowed_temperatures['middle']
        self.bottom_temps = allowed_temperatures['bottom']

    def next_node(self, node_now:DNode, store_heat_in:float, print_detail:bool=False) -> DNode:
        if store_heat_in > 0:
            if print_detail: print(f"Charge {node_now} by {store_heat_in}")
            next_node = self.charge(node_now, store_heat_in, print_detail)
        elif store_heat_in < -1:
            if print_detail: print(f"Discharge {node_now} by {-store_heat_in}")
            next_node = self.discharge(node_now, store_heat_in, print_detail)
        else:
            if print_detail: print("IDLE")
            tmb = (node_now.top_temp, node_now.middle_temp, node_now.bottom_temp)
            th = (node_now.thermocline1, node_now.thermocline2)
            next_node = self.nodes_by[tmb][th]
        return next_node
    
    def discharge(self, n: DNode, store_heat_in: float, print_detail: bool) -> DNode:
        next_node_energy = n.energy + store_heat_in
        candidate_nodes: List[DNode] = []
        if print_detail: print(f"Current energy {round(n.energy,2)}, looking for {round(next_node_energy,2)}")
        # Starting from current node
        th1 = n.thermocline1-1
        th2 = n.thermocline2-1

        # Node to discharge is a cold node
        if n.top_temp <= 100:
            if n.top_temp==80 and th1==0:
                return min(self.nodes, key=lambda x: x.energy)
            # Go through the top being at 100 or at 80
            while th1>0:
                if print_detail: print(f"Looking for {n.top_temp}({th1}){n.middle_temp}({th2}){n.bottom_temp}")
                tmb = (n.top_temp, n.middle_temp, n.bottom_temp)
                th = (th1, th2)
                node = self.nodes_by[tmb][th]
                if print_detail: print(f"Energy: {round(node.energy,2)}")
                th1 += -1
                th2 += -1
                candidate_nodes.append(node)
                if next_node_energy >= node.energy:
                    break
            # If the top was at 100 try now 80
            if n.top_temp == 100:
                th1 = self.params.num_layers
                th2 = self.params.num_layers
                while th1>0:
                    if print_detail: print(f"Looking for {n.top_temp-20}({th1}){n.middle_temp-20}({th2}){n.bottom_temp-20}")
                    tmb = (80, 60, 60)
                    th = (th1, th2)
                    node = self.nodes_by[tmb][th]
                    if print_detail: print(f"Energy: {round(node.energy,2)}")
                    th1 += -1
                    th2 += -1
                    candidate_nodes.append(node)
                    if next_node_energy >= node.energy:
                        break
            closest_node = min([x for x in candidate_nodes], key=lambda x: abs(x.energy-next_node_energy))
            return closest_node

        need_to_break = False
        while True:
            # Moving up step by step until the end of the top layer
            while th1>0:
                if print_detail: print(f"Looking for {n.top_temp}({th1}){n.middle_temp}({th2}){n.bottom_temp}")
                tmb = (n.top_temp, n.middle_temp, n.bottom_temp)
                th = (th1, th2)
                node = self.nodes_by[tmb][th]
                if print_detail: print(f"Energy: {round(node.energy,2)}")
                th1 += -1
                th2 += -1
                candidate_nodes.append(node)
                if next_node_energy >= node.energy:
                    need_to_break = True
                    break
            if need_to_break: break

            # There is no middle layer (cold nodes reached)
            if n.middle_temp == n.bottom_temp or (n.bottom_temp==100 and th1==th2):
                # Go through the top being at 100
                top_temp = 100
                middle_temp = 80
                bottom_temp = 80
                th1 = self.params.num_layers
                th2 = self.params.num_layers
                while th1>0:
                    if print_detail: print(f"Looking for {top_temp}({th1}){middle_temp}({th2}){bottom_temp}")
                    tmb = (top_temp, middle_temp, bottom_temp)
                    th = (th1, th2)
                    node = self.nodes_by[tmb][th]
                    if print_detail: print(f"Energy: {round(node.energy,2)}")
                    th1 += -1
                    th2 += -1
                    candidate_nodes.append(node)
                    if next_node_energy >= node.energy:
                        break
                # Go through the top being at 80
                top_temp = 80
                middle_temp = 60
                bottom_temp = 60
                th1 = self.params.num_layers
                th2 = self.params.num_layers
                while th1>0:
                    if print_detail: print(f"Looking for {top_temp}({th1}){middle_temp}({th2}){bottom_temp}")
                    tmb = (top_temp, middle_temp, bottom_temp)
                    th = (th1, th2)
                    node = self.nodes_by[tmb][th]
                    if print_detail: print(f"Energy: {round(node.energy,2)}")
                    th1 += -1
                    th2 += -1
                    candidate_nodes.append(node)
                    if next_node_energy >= node.energy:
                        break
                closest_node = min([x for x in candidate_nodes], key=lambda x: abs(x.energy-next_node_energy))
                return closest_node

            # Moving up step by step until the end of the middle layer
            top_temp = n.middle_temp
            th1 = th2
            while th1>0:
                if print_detail: print(f"Looking for {top_temp}({th1})-({th2}){n.bottom_temp}")
                node = [
                    x for x in self.nodes
                    if x.top_temp==top_temp
                    and x.bottom_temp==n.bottom_temp
                    and x.thermocline1==th1
                    and x.thermocline2==th2
                ][0]
                if print_detail: print(f"Energy: {round(node.energy,2)}")
                th1 += -1
                th2 += -1
                candidate_nodes.append(node)
                if next_node_energy >= node.energy:
                    break
            break

        # Find the candidate node which has closest energy to the target
        closest_node = min([x for x in candidate_nodes], key=lambda x: abs(x.energy-next_node_energy))
        return closest_node
        
    def charge(self, n: DNode, store_heat_in: float, print_detail: bool) -> DNode:
        next_node_energy = n.energy + store_heat_in

        # Charging from cold states
        if n.top_temp<=100:
            next_node_top_temp = n.top_temp
            next_node_bottom_temp = n.bottom_temp
            next_node_thermocline = self.find_thermocline(next_node_top_temp, next_node_bottom_temp, next_node_energy)
            if next_node_thermocline > self.params.num_layers and n.top_temp == 80:
                next_node_top_temp = 100
                next_node_bottom_temp = 80
                next_node_thermocline = self.find_thermocline(next_node_top_temp, next_node_bottom_temp, next_node_energy)
            # Need to rise above cold states
            if next_node_thermocline > self.params.num_layers:
                # At this point we know we have
                next_node_top_temp = 110
                next_node_bottom_temp = 100

        else:
            # If there is a bottom layer
            if n.thermocline2 < self.params.num_layers:
                heated_bottom = n.bottom_temp + self.params.delta_T(n.bottom_temp)
                if print_detail: print(f"heated_bottom = {heated_bottom}")

                # Find the new top temperature after mixing (or not)
                if heated_bottom < n.top_temp:
                    top_and_middle_mixed = (n.top_temp*n.thermocline1 + n.middle_temp*(n.thermocline2-n.thermocline1))/n.thermocline2
                    if print_detail: print(f"top_and_middle_mixed = {top_and_middle_mixed}")
                    top_and_middle_and_heated_bottom_mixed = (
                        (top_and_middle_mixed*n.thermocline2 + heated_bottom*(self.params.num_layers-n.thermocline2))/self.params.num_layers
                        )
                    if print_detail: print(f"top_and_middle_and_heated_bottom_mixed = {round(top_and_middle_and_heated_bottom_mixed,1)}")
                    next_node_top_temp = round(top_and_middle_and_heated_bottom_mixed)
                else:
                    next_node_top_temp = heated_bottom   
                
                # Bottom layer stays the same
                next_node_bottom_temp = n.bottom_temp

            # If there is no bottom layer but there is a middle layer
            elif n.thermocline1 < self.params.num_layers:     
                heated_middle = n.middle_temp + self.params.delta_T(n.middle_temp)
                if print_detail: print(f"heated_middle = {heated_middle}")

                # Find the new top temperature after mixing (or not)
                if heated_middle < n.top_temp:
                    top_and_heated_middle_mixed = (
                        (n.top_temp*n.thermocline1 + heated_middle*(self.params.num_layers-n.thermocline1))/self.params.num_layers
                        )
                    if print_detail: print(f"top_and_heated_middle_mixed = {round(top_and_heated_middle_mixed,1)}")
                    next_node_top_temp = round(top_and_heated_middle_mixed)
                else:
                    next_node_top_temp = heated_middle   

                # Bottom layer is the middle
                next_node_bottom_temp = n.middle_temp

            # If there is only a top layer
            else:
                heated_top = n.top_temp + self.params.delta_T(n.top_temp)
                if print_detail: print(f"heated_top = {heated_top}")
                next_node_top_temp = heated_top   
                # Bottom layer is the top
                next_node_bottom_temp = n.top_temp

        # Starting with that top and current bottom, find the thermocline position that matches the next node energy
        next_node_thermocline = self.find_thermocline(next_node_top_temp, next_node_bottom_temp, next_node_energy)
        if print_detail: print(f"Next node ({next_node_top_temp}, {next_node_bottom_temp}) thermocline: {next_node_thermocline}")
        while next_node_thermocline > self.params.num_layers:
            next_node_bottom_temp = next_node_top_temp
            next_node_top_temp = round(next_node_top_temp + self.params.delta_T(next_node_top_temp))
            next_node_thermocline = self.find_thermocline(next_node_top_temp, next_node_bottom_temp, next_node_energy)
            if print_detail: print(f"Next node ({next_node_top_temp}, {next_node_bottom_temp}) thermocline: {next_node_thermocline}")

        if next_node_top_temp <= 100:
            node_next_true = DNode(
                parameters = self.params,
                top_temp = next_node_top_temp,
                middle_temp = next_node_bottom_temp,
                bottom_temp = next_node_bottom_temp,
                thermocline1 = next_node_thermocline,
                thermocline2 = next_node_thermocline,
            )
        
        else:
            if next_node_bottom_temp != 100:
                if next_node_thermocline > 0:
                    node_next_true = DNode(
                        parameters = self.params,
                        top_temp = next_node_top_temp,
                        middle_temp = next_node_bottom_temp,
                        bottom_temp = n.bottom_temp,
                        thermocline1 = next_node_thermocline,
                        thermocline2 = self.params.num_layers,
                    )
                else:
                    node_next_true = DNode(
                        parameters = self.params,
                        top_temp = next_node_bottom_temp,
                        middle_temp = next_node_bottom_temp-10 if next_node_bottom_temp>=120 else 100,
                        bottom_temp = n.bottom_temp,
                        thermocline1 = self.params.num_layers,
                        thermocline2 = self.params.num_layers,
                    )
            else:
                node_next_true = DNode(
                    parameters = self.params,
                    top_temp = next_node_top_temp,
                    middle_temp = next_node_top_temp,
                    bottom_temp = next_node_bottom_temp,
                    thermocline1 = next_node_thermocline,
                    thermocline2 = next_node_thermocline
                )

        node_next = self.find_closest_node(node_next_true, print_detail)
        if print_detail: print(f"True: {node_next_true}, associated to {node_next}")
        return node_next
        
    def find_thermocline(self, top_temp, bottom_temp, energy):
        top, bottom = to_kelvin(top_temp), to_kelvin(bottom_temp)
        m_layer_kg = self.params.storage_volume*3.785 / self.params.num_layers    
        if top==bottom: top+=1  
        return int(1/(top-bottom)*(energy/(m_layer_kg*4.187/3600)-(-0.5*top+(self.params.num_layers+0.5)*bottom)))
        
    def find_closest_node(self, true_n: DNode, print_detail: bool) -> DNode:
        if print_detail: print(f"Looking for closest of {true_n}")

        # Cold nodes
        if true_n.top_temp <= 100:
            nodes_with_similar_temps = [
                n for n in self.nodes if 
                n.top_temp==true_n.top_temp and 
                n.middle_temp==true_n.top_temp-20 and 
                n.bottom_temp==true_n.top_temp-20 and
                n.thermocline1==true_n.thermocline1 and
                n.thermocline2==true_n.thermocline2
            ]
            closest_node = min(nodes_with_similar_temps, key = lambda x: abs(x.energy-true_n.energy))
            return closest_node

        # Find closest available top, middle and bottom temps
        closest_top_temp = min(self.top_temps, key=lambda x: abs(float(x)-true_n.top_temp))
        closest_middle_temp = min(self.middle_temps, key=lambda x: abs(float(x)-true_n.middle_temp))
        closest_bottom_temp = min(self.bottom_temps, key=lambda x: abs(float(x)-true_n.bottom_temp))

        # Need at least 10F between top and middle
        if closest_top_temp - closest_middle_temp < 10:
            closest_middle_temp = closest_top_temp-10 if closest_top_temp>115 else 100

        # Correct for the 120,100,100 case
        if closest_top_temp == 120 and closest_middle_temp==100:
            closest_middle_temp = 110

        if print_detail: print(f"{closest_top_temp},{closest_middle_temp},{closest_bottom_temp}")

        # Top temperature is impossible to reach
        if true_n.top_temp > max(self.top_temps):
            nodes_with_similar_temps = [
                n for n in self.nodes if 
                n.top_temp == max(self.top_temps) and
                n.middle_temp==closest_middle_temp and
                n.bottom_temp==closest_bottom_temp and
                n.thermocline2==true_n.thermocline2
            ]
            closest_node = min(nodes_with_similar_temps, key = lambda x: abs(x.energy-true_n.energy))
            return closest_node

        # Both top and middle were rounded above
        if closest_top_temp > true_n.top_temp and closest_middle_temp > true_n.middle_temp:
            nodes_with_similar_temps = [
                n for n in self.nodes if 
                n.top_temp<=closest_top_temp and
                n.top_temp>=closest_top_temp-10 and
                n.middle_temp<=closest_middle_temp and
                n.middle_temp>=closest_middle_temp-10 and
                n.bottom_temp==closest_bottom_temp and
                n.thermocline2==true_n.thermocline2
            ]
            closest_node = min(nodes_with_similar_temps, key = lambda x: abs(x.energy-true_n.energy))
            return closest_node
        
        # Both top and middle were rounded below
        if closest_top_temp < true_n.top_temp and closest_bottom_temp < true_n.middle_temp:
            nodes_with_similar_temps = [
                n for n in self.nodes if 
                n.top_temp<=closest_top_temp+10 and
                n.top_temp>=closest_top_temp and
                n.middle_temp<=closest_middle_temp+10 and
                n.middle_temp>=closest_middle_temp and
                n.bottom_temp==closest_bottom_temp and
                n.thermocline2==true_n.thermocline2
            ]
            closest_node = min(nodes_with_similar_temps, key = lambda x: abs(x.energy-true_n.energy))
            return closest_node

        # Top was rounded above but not middle: flexible th1
        if closest_top_temp > true_n.top_temp:
            nodes_with_similar_temps = [
                n for n in self.nodes if 
                n.top_temp==closest_top_temp and
                n.middle_temp==closest_middle_temp and
                n.bottom_temp==closest_bottom_temp and
                n.thermocline2==true_n.thermocline2
            ]
            closest_node = min(nodes_with_similar_temps, key = lambda x: abs(x.energy-true_n.energy))
            return closest_node

        # Middle was rounded above but not top: flexible th2
        if closest_top_temp > true_n.top_temp:
            nodes_with_similar_temps = [
                n for n in self.nodes if 
                n.top_temp==closest_top_temp and
                n.middle_temp==closest_middle_temp and
                n.bottom_temp==closest_bottom_temp and
                n.thermocline1==true_n.thermocline1
            ]
            closest_node = min(nodes_with_similar_temps, key = lambda x: abs(x.energy-true_n.energy))
            return closest_node

        nodes_with_similar_temps = [
            n for n in self.nodes if 
            n.top_temp==closest_top_temp and 
            n.middle_temp==closest_middle_temp and 
            n.bottom_temp==closest_bottom_temp and
            n.thermocline1==true_n.thermocline1 and
            n.thermocline2==true_n.thermocline2
        ]
        closest_node = min(nodes_with_similar_temps, key = lambda x: abs(x.energy-true_n.energy))
        return closest_node