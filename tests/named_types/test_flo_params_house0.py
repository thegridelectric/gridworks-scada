import pprint
import json
from pathlib import Path

from gwsproto.named_types import FloParamsHouse0, BidRecommendation
from gridflo import Flo

#if __name__ == "__main__":
import pprint
#params_path = Path(__file__).parent / "flo_params.json"
params_path = Path("tests/flo_params.json")
data = json.loads(params_path.read_text())
flo_params = FloParamsHouse0.model_validate(data)
flo_param_bytes = flo_params.model_dump_json().encode('utf-8')
flo = Flo(flo_param_bytes)
flo.solve_dijkstra()
br_bytes = flo.generate_recommendation(flo_param_bytes)
br_dict = json.loads(br_bytes)
br = BidRecommendation.model_validate(br_dict)
pprint.pp(br.model_dump())


import json
from pathlib import Path

from gridflo import Flo
from gridflo.asl.types import BidRecommendation, FloParamsHouse0

params_path = Path("tests/flo_params.json")
flo_params = FloParamsHouse0.from_dict(json.loads(params_path.read_text()))
flo_param_bytes = flo_params.to_bytes()
flo = Flo(flo_params.to_bytes())
flo.solve_dijkstra()
br_bytes = flo.generate_recommendation(flo_params.to_bytes())
br = BidRecommendation.from_bytes(br_bytes)
pprint.pp(br.to_dict())