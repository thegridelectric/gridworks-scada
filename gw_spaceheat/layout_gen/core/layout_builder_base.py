from __future__ import annotations

from gwsproto.enums import (ActorClass, EmissionMethod, GwQuantity, GwUnit,
                            TelemetryName)
from gwsproto.named_types import (DataChannelGt, DerivedChannelGt,
                                  SpaceheatNodeGt)
from gwsproto.property_format import SpaceheatName, UUID4Str, HandleName
from layout_gen.core.layout_db import LayoutDb


def add_spaceheat_node(
    db: LayoutDb,
    *,
    name: SpaceheatName,
    actor_class: ActorClass,
    display_name: str,
    component_id: UUID4Str | None = None,
    actor_hierarchy_name: HandleName | None = None,
    handle: HandleName | None = None,
) -> None:
    db.add_nodes(
        [
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(name),
                Name=name,
                ActorClass=actor_class,
                DisplayName=display_name,
                ComponentId=component_id,
                ActorHierarchyName=actor_hierarchy_name,
                Handle=handle,
            )
        ]
    )


def add_data_channel(
    db: LayoutDb,
    *,
    name: str,
    about_node_name: str,
    captured_by_node_name: str,
    display_name: str,
    telemetry_name: TelemetryName,
    terminal_asset_alias: str,
) -> None:
    db.add_data_channels(
        [
            DataChannelGt(
                Name=name,
                Id=db.make_channel_id(name),
                AboutNodeName=about_node_name,
                CapturedByNodeName=captured_by_node_name,
                DisplayName=display_name,
                TelemetryName=telemetry_name,
                TerminalAssetAlias=terminal_asset_alias,
            )
        ]
    )


def add_heat_call_derived_channel(
    db: LayoutDb,
    *,
    name: str,
    created_by_node_name: str,
    input_channel_name: str,
    display_name: str,
    terminal_asset_alias: str,
    emit_period_s: int = 300,
    async_emit_delta: int = 1,
) -> None:
    db.add_derived_channels(
        [
            DerivedChannelGt(
                Id=db.make_derived_channel_id(name),
                Name=name,
                CreatedByNodeName=created_by_node_name,
                DisplayName=display_name,
                Strategy="heat-call",
                EmissionMethod=EmissionMethod.AsyncAndPeriodic,
                EmitPeriodS=emit_period_s,
                AsyncEmitDelta=async_emit_delta,
                InputChannelNames=[input_channel_name],
                OutputUnit=GwUnit.Unitless,
                OutputQuantity=GwQuantity.Unitless,
                Parameters={"Interpretation": "DigitalZeroIsActive"},
                TerminalAssetAlias=terminal_asset_alias,
            )
        ]
    )