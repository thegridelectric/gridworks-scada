import gc
import time
import json
from typing import List
from gwproactor.logger import LoggerOrAdapter
from actors.ltn.dtypes import DNode, DEdge
from gwsproto.enums import MarketPriceUnit, MarketQuantityUnit, MarketTypeName
from gwsproto.named_types import FloParamsHouse0, PriceQuantityUnitless, BidRecommendation

P_NODE = "hw1.isone.ver.keene" # TODO: add to House0Params for audit trail

class Flo():
    LOGGER_NAME="flo"
    def __init__(self, flo_params_bytes: bytes, logger: LoggerOrAdapter):
        flo_params_dict = json.loads(flo_params_bytes.decode('utf-8'))
        flo_params = FloParamsHouse0.model_validate(flo_params_dict)
        self.logger = logger
        self.flo_params = flo_params
        raise NotImplementedError("Need to populate graph before this works!")

    def create_nodes(self):
        self.nodes: dict[int, list[DNode]] = {h: [] for h in range(self.flo_params.HorizonHours+1)}
        # TODO make Dijkstra Nodes

    def create_edges(self):
        self.edges: dict[DNode, list[DEdge]] = {}
        # TODO make Dijkstra Edges
    
    def solve_dijkstra(self):
        start_time = time.time()
        try:
            for time_slice in range(self.flo_params.HorizonHours-1, -1, -1):
                for node in self.nodes[time_slice]:
                    best_edge = min(self.edges[node], key=lambda e: e.head.pathcost + e.cost)
                    node.pathcost = best_edge.head.pathcost + best_edge.cost
                    node.next_node = best_edge.head
            self.logger.info(f"Solved Dijkstra in {round(time.time()-start_time, 1)} seconds")
        except Exception as e:
            self.logger.error(f"Error solving Dijkstra algorithm: {e}")
            raise

    def find_initial_node(self, updated_flo_params: FloParamsHouse0 | None = None):
        self.initial_node: DNode = self.nodes[0][50]
        self.bid_edges: dict[DNode, list[DEdge]] = {}

    def generate_recommendation(self, flo_params_bytes: bytes | None=None) -> bytes:
        """ Returns serialized"""
        self.logger.info("Generating bid...")
        if flo_params_bytes:
            flo_params_dict = json.loads(flo_params_bytes.decode('utf-8'))
            flo_params = FloParamsHouse0.model_validate(flo_params_dict)
        self.pq_pairs: List[PriceQuantityUnitless] = []
        self.find_initial_node(flo_params)
        
        forecasted_cop = self.flo_params.COP(oat=self.flo_params.OatForecastF[0])
        forecasted_price_usd_mwh = self.flo_params.total_price_forecast[0]
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