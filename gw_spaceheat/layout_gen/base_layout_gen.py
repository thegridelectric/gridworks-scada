from __future__ import annotations

from dataclasses import dataclass
\

from gwsproto.enums import ActorClass, EmissionMethod, TelemetryName, Unit, GwUnit, GwQuantity
from gwsproto.named_types import (
    SpaceheatNodeGt,
    DataChannelGt,
    DerivedChannelGt,
)

from layout_gen.layout_db import LayoutDb


@dataclass(frozen=True)
class ZoneWhitewireNames:
    """
    Canonical naming for the 'whitewire opto input' pattern.
    """
    idx: int
    zone: str

    @property
    def zone_node(self) -> str:
        return f"zone{self.idx}-{self.zone}".lower()

    @property
    def whitewire_sensor_node(self) -> str:
        return f"{self.zone_node}-opto"

    @property
    def whitewire_data_channel(self) -> str:
        return f"{self.zone_node}-opto-input"

    @property
    def heat_call_channel(self) -> str:
        return f"{self.zone_node}-heat-call"

    @property
    def zone_display_prefix(self) -> str:
        return f"Zone {self.idx} {self.display_zone}"

    @property
    def display_zone(self) -> str:
        return " ".join(word.capitalize() for word in self.zone.split("-"))

def add_spaceheat_node(
    db: LayoutDb,
    *,
    name: str,
    actor_class: ActorClass,
    display_name: str,
    component_id: str | None = None,
    actor_hierarchy_name: str | None = None,
    handle: str | None = None,
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