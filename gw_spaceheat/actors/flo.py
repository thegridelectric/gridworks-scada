import gc
import time
import json
import numpy as np
from typing import Dict, List, Tuple
from gwproactor.logger import LoggerOrAdapter
from .dijkstra_types import DParams, DNode, DEdge
from gwsproto.named_types import FloParamsHouse0, PriceQuantityUnitless


class DGraph():
    LOGGER_NAME="flo"
    def __init__(self, flo_params: FloParamsHouse0, logger: LoggerOrAdapter):
        self.logger = logger
        self.params = DParams(flo_params)
        start_time = time.time()
        try:
            self.load_super_graph()
            self.logger.info(f"Loaded super graph in {round(time.time()-start_time, 1)} seconds")
        except Exception as e:
            self.logger.warning(f"Error with load_super_graph! {e}")
            raise
        start_time = time.time()
        try:
            self.create_nodes()
            self.logger.info(f"Created nodes in {round(time.time()-start_time, 1)} seconds")
        except Exception as e:
            self.logger.warning(f"Error with create_nodes! {e}")
            raise
        start_time = time.time()
        try:
            self.create_edges()
            self.logger.info(f"Created edges in {round(time.time()-start_time, 1)} seconds")
        except Exception as e:
            self.logger.warning(f"Error with create_edges! {e}")
            raise
        del self.super_graph
        gc.collect()
        self.logger.info("Cleared super graph from memory")
        
    def load_super_graph(self):
        with open(f"super_graph_{self.params.storage_volume}.json", 'r') as f:
            self.super_graph: Dict = json.load(f)
        self.discretized_store_heat_in = [float(x) for x in list(self.super_graph.keys())]
        self.discretized_store_heat_in_array = np.array(self.discretized_store_heat_in)

    def create_nodes(self):
        self.nodes: Dict[int, List[DNode]] = {h: [] for h in range(self.params.horizon+1)}
        self.nodes_by: Dict[int, Dict[Tuple, Dict[Tuple, DNode]]] = {h: {} for h in range(self.params.horizon+1)}
        self.bid_nodes: Dict[int, List[DNode]] = {h: [] for h in range(self.params.horizon+1)}

        super_graph_nodes: List[str] = self.super_graph['0.0']

        for node_no_time_slice in super_graph_nodes:
            t, th1, m, th2, b = self.read_node_str(node_no_time_slice)

            for h in range(self.params.horizon+1):
                node = DNode(
                    time_slice=h,
                    top_temp=t,
                    middle_temp=m,
                    bottom_temp=b,
                    thermocline1=th1,
                    thermocline2=th2,
                    parameters=self.params
                )

                self.nodes[h].append(node)
                if h==0:
                    self.bid_nodes[h].append(node)
                if h==0 and (t,m,b) not in self.nodes_by[h]:
                    for hour in range(self.params.horizon+1):
                        self.nodes_by[hour][(t,m,b)] = {}
                self.nodes_by[h][(t,m,b)][(th1,th2)] = node
                
        self.logger.info(f"Built a graph with {self.params.horizon} layers of {len(self.nodes[0])} nodes each")
        self.min_node_energy = min(self.nodes[0], key=lambda n: n.energy).energy
        self.max_node_energy = max(self.nodes[0], key=lambda n: n.energy).energy

    def create_edges(self):
        self.edges: Dict[DNode, List[DEdge]] = {}
        self.bid_edges: Dict[DNode, List[DEdge]] = {}

        current_state = DNode(
            top_temp=self.params.initial_top_temp,
            middle_temp=self.params.initial_middle_temp,
            bottom_temp=self.params.initial_bottom_temp,
            thermocline1=self.params.initial_thermocline1,
            thermocline2=self.params.initial_thermocline2,
            parameters=self.params
        )

        # If more than half of top above 170, and no water colder than 170-deltaT, storage considered full
        self.storage_is_currently_full = False
        half_above_170 = (
            (current_state.top_temp>170 and current_state.thermocline1>=self.params.num_layers/2) 
            or (current_state.middle_temp>=170 and current_state.thermocline2>=self.params.num_layers/2)
        )
        cold_water_available = (
            (current_state.thermocline2-current_state.thermocline1>0 and current_state.middle_temp<170-self.params.delta_T(170))
            or (self.params.num_layers-current_state.thermocline2>0 and current_state.bottom_temp<170-self.params.delta_T(170))
        )
        if half_above_170 and not cold_water_available:
            print(f"Storage is currently full.")
            self.storage_is_currently_full = True

        for h in range(self.params.horizon):

            load = self.params.load_forecast[h]
            rswt = self.params.rswt_forecast[h]
            cop = self.params.COP(oat=self.params.oat_forecast[h])

            turn_on_minutes = self.params.hp_turn_on_minutes if h==0 else self.params.hp_turn_on_minutes/2
            max_hp_elec_in = ((1-turn_on_minutes/60) if (h==0 and self.params.hp_is_off) else 1) * self.params.max_hp_elec_in
            max_hp_heat_out = max_hp_elec_in * cop
            
            for node_now in self.nodes[h]:
                self.edges[node_now] = []
                if h==0:
                    self.bid_edges[node_now] = []

                losses = self.params.storage_losses_percent/100 * (node_now.energy-self.min_node_energy)
                
                # Can not put out more heat than what would fill the storage
                store_heat_in_for_full = self.max_node_energy - node_now.energy
                hp_heat_out_for_full = store_heat_in_for_full + load + losses
                if hp_heat_out_for_full < max_hp_heat_out:
                    hp_heat_out_levels = [0, hp_heat_out_for_full] if hp_heat_out_for_full > 10 else [0]
                else:
                    hp_heat_out_levels = [0, max_hp_heat_out]
                # If the HP is already on, add the "meet the load" edge in the first hour
                if h==0 and load>0 and not self.params.hp_is_off:
                    hp_heat_out_levels += [load+losses]
                
                for hp_heat_out in hp_heat_out_levels:
                    store_heat_in = hp_heat_out - load - losses
                    closest_store_heat_in = self.discretized_store_heat_in[abs(self.discretized_store_heat_in_array-store_heat_in).argmin()]
                    
                    node_next_str: str = self.super_graph[str(closest_store_heat_in)][node_now.to_string()]
                    t, th1, m, th2, b = self.read_node_str(node_next_str)
                    node_next = self.nodes_by[node_now.time_slice+1][(t,m,b)][(th1,th2)]

                    if self.storage_is_currently_full and node_next.energy>current_state.energy:
                        t, m, b = node_now.top_temp, node_now.middle_temp, node_now.bottom_temp
                        th1, th2 = node_now.thermocline1, node_now.thermocline2
                        node_next = self.nodes_by[node_now.time_slice+1][(t,m,b)][(th1,th2)]

                    cost = self.params.elec_price_forecast[h]/100 * hp_heat_out/cop
                    if store_heat_in<0 and load>0 and (node_now.top_temp<rswt or node_next.top_temp<rswt):
                        cost += 1e5

                    self.edges[node_now].append(DEdge(node_now, node_next, cost, hp_heat_out))
                    if h==0:
                        self.bid_edges[node_now].append(DEdge(node_now, node_next, cost, hp_heat_out))

            print(f"Built edges for hour {h}")
    
    def solve_dijkstra(self):
        start_time = time.time()
        try:
            for time_slice in range(self.params.horizon-1, -1, -1):
                for node in self.nodes[time_slice]:
                    best_edge = min(self.edges[node], key=lambda e: e.head.pathcost + e.cost)
                    node.pathcost = best_edge.head.pathcost + best_edge.cost
                    node.next_node = best_edge.head
            self.logger.info(f"Solved Dijkstra in {round(time.time()-start_time, 1)} seconds")
        except Exception as e:
            self.logger.error(f"Error solving Dijkstra algorithm: {e}")
            raise

    def read_node_str(self, node_str: str):
        parts = node_str.replace(')', '(').split('(')
        top, thermocline1, middle, thermocline2, bottom = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
        return top, thermocline1, middle, thermocline2, bottom

    def find_initial_node(self, updated_flo_params: FloParamsHouse0=None):
        if updated_flo_params:
            self.params = DParams(updated_flo_params)
        
        self.initial_state = DNode(
            top_temp=self.params.initial_top_temp,
            middle_temp=self.params.initial_middle_temp,
            bottom_temp=self.params.initial_bottom_temp,
            thermocline1=self.params.initial_thermocline1,
            thermocline2=self.params.initial_thermocline2,
            parameters=self.params
        )

        top_temps = set([n.top_temp for n in self.bid_nodes[0]])
        closest_top_temp = min(top_temps, key=lambda x: abs(x-self.initial_state.top_temp))

        bottom_temps = set([n.bottom_temp for n in self.bid_nodes[0] if n.top_temp==closest_top_temp])
        closest_bottom_temp = min(bottom_temps, key=lambda x: abs(x-self.initial_state.bottom_temp))

        middle_temps = set([n.middle_temp for n in self.bid_nodes[0] if n.top_temp==closest_top_temp  and n.bottom_temp==closest_bottom_temp])
        closest_middle_temp = min(middle_temps, key=lambda x: abs(x-self.initial_state.middle_temp))

        nodes_with_similar_temperatures = [
            n for n in self.bid_nodes[0]
            if n.top_temp == closest_top_temp
            and n.middle_temp == closest_middle_temp
            and n.bottom_temp == closest_bottom_temp
        ]

        thermoclines1 = set([n.thermocline1 for n in nodes_with_similar_temperatures])
        closest_thermocline1 = min(thermoclines1, key=lambda x: abs(x-self.initial_state.thermocline1))

        similar_nodes = [
            n for n in nodes_with_similar_temperatures
            if n.thermocline1 == closest_thermocline1
        ]

        if abs(self.initial_state.top_temp - self.initial_state.middle_temp) <= 5 and abs(self.initial_state.top_temp - self.initial_state.bottom_temp) > 5:
            similar_nodes = [
                n for n in self.bid_nodes[0]
                if n.top_temp == closest_top_temp
                and n.thermocline1 == 16
                and n.thermocline2 == 24
            ]
            if not similar_nodes:
                similar_nodes = [
                    n for n in self.bid_nodes[0]
                    if n.top_temp == closest_top_temp
                    and n.thermocline1 == 16
                ]

        self.initial_node = min(
            similar_nodes, 
            key=lambda x: abs(x.energy-self.initial_state.energy)
        )
        print(f"Initial state: {self.initial_state}")
        print(f"Initial node: {self.initial_node}")

        for e in self.bid_edges[self.initial_node]:
            if self.storage_is_currently_full and e.head.energy > self.initial_node.energy:
                self.bid_edges[self.initial_node].remove(e)
                print(f"Removed edge {e} because the storage is already close to full.")

    def generate_bid(self, updated_flo_params: FloParamsHouse0=None):
        self.logger.info("Generating bid...")
        self.pq_pairs: List[PriceQuantityUnitless] = []
        self.find_initial_node(updated_flo_params)
        
        forecasted_cop = self.params.COP(oat=self.params.oat_forecast[0])
        forecasted_price_usd_mwh = self.params.elec_price_forecast[0]*10
        price_range_usd_mwh = sorted(list(range(-100, 2000)) + [forecasted_price_usd_mwh])
        edge_cost = {}

        for price_usd_mwh in price_range_usd_mwh:
            for edge in self.bid_edges[self.initial_node]:
                edge_cost[edge] = edge.cost if edge.cost >= 1e4 else edge.hp_heat_out/forecasted_cop * price_usd_mwh/1000
            best_edge: DEdge = min(self.bid_edges[self.initial_node], key=lambda e: e.head.pathcost + edge_cost[e])
            best_quantity_kwh = max(0, best_edge.hp_heat_out/forecasted_cop)
            if not self.pq_pairs or (self.pq_pairs[-1].QuantityTimes1000-int(best_quantity_kwh*1000)>10):
                self.pq_pairs.append(
                    PriceQuantityUnitless(
                        PriceTimes1000 = int(price_usd_mwh * 1000),
                        QuantityTimes1000 = int(best_quantity_kwh * 1000))
                )
        self.logger.info(f"Done ({len(self.pq_pairs)} PQ pairs found).")

    def trim_graph_for_waiting(self):
        """Remove all but the first two time slices to save memory while waiting to generate bid."""
        start_time = time.time()
        del self.nodes_by
        del self.nodes
        del self.edges
        gc.collect()
        self.logger.info(f"Trimmed graph in {round(time.time()-start_time, 1)} seconds.")