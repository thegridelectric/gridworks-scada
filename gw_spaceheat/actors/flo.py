import gc
import time
import json
import numpy as np
from typing import Dict, List, Tuple
from gwproactor.logger import LoggerOrAdapter
from .dtypes import DParams, DNode, DEdge
from gwsproto.enums import MarketPriceUnit, MarketQuantityUnit, MarketTypeName
from gwsproto.named_types import FloParamsHouse0, PriceQuantityUnitless, BidRecommendation

P_NODE = "hw1.isone.ver.keene" # TODO: add to House0Params for audit trail

class DGraph():
    LOGGER_NAME="flo"
    def __init__(self, flo_params_bytes: bytes, logger: LoggerOrAdapter):
        flo_params_dict = json.loads(flo_params_bytes.decode('utf-8'))
        flo_params = FloParamsHouse0.model_validate(flo_params_dict)
        self.logger = logger
        self.flo_params = flo_params
        self.params = DParams(flo_params)
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

    def create_nodes(self):
        self.nodes: Dict[int, List[DNode]] = {h: [] for h in range(self.params.horizon+1)}
        self.bid_nodes: Dict[int, List[DNode]] = {h: [] for h in range(self.params.horizon+1)}
        ... # TODO
        self.logger.info(f"Built a graph with {self.params.horizon} layers of {len(self.nodes[0])} nodes each")
        self.min_node_energy = min(self.nodes[0], key=lambda n: n.energy).energy
        self.max_node_energy = max(self.nodes[0], key=lambda n: n.energy).energy

    def create_edges(self):
        self.edges: Dict[DNode, List[DEdge]] = {}
        self.bid_edges: Dict[DNode, List[DEdge]] = {}

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
                
                for hp_heat_out in hp_heat_out_levels:
                    store_heat_in = hp_heat_out - load - losses
                    node_next = ... # TODO

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

    def find_initial_node(self, updated_flo_params: FloParamsHouse0 | None =None):
        if updated_flo_params:
            self.params = DParams(updated_flo_params)
        self.initial_node = ... # TODO
        print(f"Initial state: {self.initial_state}")
        print(f"Initial node: {self.initial_node}")

    def generate_recommendation(self, flo_params_bytes: bytes | None=None) -> bytes:
        """ Returns serialized"""
        self.logger.info("Generating bid...")
        if flo_params_bytes:
            flo_params_dict = json.loads(flo_params_bytes.decode('utf-8'))
            flo_params = FloParamsHouse0.model_validate(flo_params_dict)
        self.pq_pairs: List[PriceQuantityUnitless] = []
        self.find_initial_node(flo_params)
        
        forecasted_cop = self.params.COP(oat=self.params.oat_forecast[0])
        forecasted_price_usd_mwh = self.params.elec_price_forecast[0]*10
        price_range_usd_mwh = sorted(list(range(-100, 2000)) + [forecasted_price_usd_mwh])
        edge_cost = {}

        for price_usd_mwh in price_range_usd_mwh:
            for edge in self.bid_edges[self.initial_node]:
                edge_cost[edge] = edge.cost if edge.cost >= 1e4 else edge.hp_heat_out/forecasted_cop * price_usd_mwh/1000
            best_edge: DEdge = min(self.bid_edges[self.initial_node], key=lambda e: e.head.pathcost + edge_cost[e])
            best_quantity_kwh = max(0, best_edge.hp_heat_out/forecasted_cop)
            if not self.pq_pairs or (self.pq_pairs[-1].QuantityX1000-int(best_quantity_kwh*1000)>10):
                self.pq_pairs.append(
                    PriceQuantityUnitless(
                        PriceX1000 = int(price_usd_mwh * 1000),
                        QuantityX1000 = int(best_quantity_kwh * 1000))
                )
        self.logger.info(f"Done ({len(self.pq_pairs)} PQ pairs found).")
        slot_start_s = flo_params.StartUnixS
        mtn = MarketTypeName.rt60gate5.value # TODO: send in House0FloParams
        market_slot_name = f"e.{mtn}.{P_NODE}.{slot_start_s}"

        return BidRecommendation(
            BidderAlias=self.flo_params.GNodeAlias,
            MarketSlotName=market_slot_name,
            PqPairs=self.pq_pairs,
            InjectionIsPositive=True,
            PriceUnit=MarketPriceUnit.USDPerMWh,
            QuantityUnit=MarketQuantityUnit.AvgkW
        ).model_dump_json().encode('utf-8')

    def trim_graph_for_waiting(self):
        """Remove all but the first two time slices to save memory while waiting to generate bid."""
        start_time = time.time()
        del self.nodes
        del self.edges
        gc.collect()
        self.logger.info(f"Trimmed graph in {round(time.time()-start_time, 1)} seconds.")