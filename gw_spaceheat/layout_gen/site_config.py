import uuid
from pydantic import BaseModel

from layout_gen.core.layout_db import LayoutDb
from gwsproto.enums import FlowManifoldVariant
from gwsproto.property_format import LeftRightDotStr

class SiteConfig(BaseModel):
    ltn_alias: LeftRightDotStr
    strategy: str = "House0"
    flow_manifold_variant: FlowManifoldVariant = FlowManifoldVariant.House0
    use_sieg_loop: bool = False


def apply_site_config(db: LayoutDb, cfg: SiteConfig) -> None:
    # -------------------------
    # GNodes (idempotent)
    # -------------------------
    if not db.misc.get("MyLeafTransactiveNodeGNode"):
        db.misc["MyLeafTransactiveNodeGNode"] = {
            "GNodeId": str(uuid.uuid4()),
            "Alias": cfg.ltn_alias,
            "DisplayName": "LeafTransactiveNode",
            "GNodeStatus": "Active",
            "GNodeClass": "LeafTransactiveNode",
        }

        db.misc["MyScadaGNode"] = {
            "GNodeId": str(uuid.uuid4()),
            "Alias": f"{cfg.ltn_alias}.scada",
            "DisplayName": "Scada GNode",
            "GNodeStatus": "Active",
            "GNodeClass": "Scada",
        }

        db.misc["MyTerminalAssetGNode"] = {
            "GNodeId": str(uuid.uuid4()),
            "Alias": f"{cfg.ltn_alias}.ta",
            "DisplayName": "TerminalAsset GNode",
            "GNodeStatus": "Active",
            "GNodeClass": "TerminalAsset",
        }

    # -------------------------
    # Strategy / system flags
    # -------------------------
    db.misc["Strategy"] = cfg.strategy
    db.misc["FlowManifoldVariant"] = cfg.flow_manifold_variant
    db.misc["UseSiegLoop"] = cfg.use_sieg_loop