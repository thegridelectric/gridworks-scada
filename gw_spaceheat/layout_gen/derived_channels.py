from pydantic import BaseModel
from typing import Sequence

from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import EmissionMethod, GwUnit, HeatCallInterpretation
from layout_gen.layout_db import LayoutDb
from gwsproto.named_types import DerivedChannelGt
# TODO: add to H0N and H0CN

class DerivedChConfig(BaseModel):
    Name: str
    CreatedByNodeName: str 
    Strategy: str
    OutputUnit: GwUnit
    
def add_derived_channel(db: LayoutDb, derived_cfg: DerivedChConfig) -> None:
    db.add_derived_channels(
        [DerivedChannelGt(
            Id = db.make_derived_channel_id(derived_cfg.Name),
            Name = derived_cfg.Name,
            CreatedByNodeName = derived_cfg.CreatedByNodeName,
            OutputUnit=derived_cfg.OutputUnit, 
            TerminalAssetAlias = db.terminal_asset_alias,
            Strategy = derived_cfg.Strategy,
            DisplayName = f"{derived_cfg.Name.title().replace('-','')} {derived_cfg.OutputUnit}",
            )
        ]
    )


def _zone_items(
    db: LayoutDb,
    zone_names: Sequence[str] | dict[int, str] | None,
) -> list[tuple[int, str]]:
    if zone_names is None:
        zone_names = list(db.misc.get("ZoneList", db.loaded.zone_list))

    if isinstance(zone_names, dict):
        return sorted(zone_names.items())

    return list(enumerate(zone_names, start=1))


def _zone_base(zone_idx: int, zone_name: str) -> str:
    return f"zone{zone_idx}-{zone_name}".lower()


def _add_zone_heat_call_channel(
    db: LayoutDb,
    *,
    zone_idx: int,
    zone_name: str,
    input_channel_name: str | None = None,
    interpretation: HeatCallInterpretation | str = HeatCallInterpretation.DigitalZeroIsActive,
    threshold: float | None = None,
    emit_period_s: int = 300,
) -> None:
    zone_base = _zone_base(zone_idx, zone_name)
    if input_channel_name is None:
        input_channel_name = f"{zone_base}-opto-input"

    params = {"Interpretation": HeatCallInterpretation(interpretation).value}
    if threshold is not None:
        params["Threshold"] = threshold

    db.add_derived_channels(
        [
            DerivedChannelGt(
                Id=db.make_derived_channel_id(f"{zone_base}-heat-call"),
                Name=f"{zone_base}-heat-call",
                CreatedByNodeName=H0N.derived_generator,
                Strategy="heat-call",
                InputChannelNames=[input_channel_name],
                OutputUnit=GwUnit.Unitless,
                EmissionMethod=EmissionMethod.AsyncAndPeriodic,
                AsyncEmitDelta=1,
                EmitPeriodS=emit_period_s,
                Parameters=params,
                DisplayName=(
                    f"Zone {zone_idx} {zone_name.replace('-', ' ').title()} "
                    "Heat Call"
                ),
                TerminalAssetAlias=db.terminal_asset_alias,
            )
        ]
    )


def add_zone_heat_call_channels(
    db: LayoutDb,
    *,
    zone_names: Sequence[str] | dict[int, str] | None = None,
    input_channel_names: dict[int, str] | None = None,
    interpretation: HeatCallInterpretation | str = HeatCallInterpretation.DigitalZeroIsActive,
    threshold: float | None = None,
    emit_period_s: int = 300,
) -> None:
    """Add zone{x}-{zone-name}-heat-call channels from zone opto inputs."""
    input_channel_names = input_channel_names or {}

    for zone_idx, zone_name in _zone_items(db, zone_names):
        _add_zone_heat_call_channel(
            db,
            zone_idx=zone_idx,
            zone_name=zone_name,
            input_channel_name=input_channel_names.get(zone_idx),
            interpretation=interpretation,
            threshold=threshold,
            emit_period_s=emit_period_s,
        )


def _add_zone_predicted_setpoint_channel(
    db: LayoutDb,
    *,
    zone_idx: int,
    zone_name: str,
    gw_temp_channel_name: str | None = None,
    heat_call_channel_name: str | None = None,
    threshold_f: float = 2.0,
    async_emit_delta_f: float = 0.2,
    emit_period_s: int = 300,
) -> None:
    zone_base = _zone_base(zone_idx, zone_name)
    if gw_temp_channel_name is None:
        gw_temp_channel_name = f"{zone_base}-gw-temp"
    if heat_call_channel_name is None:
        heat_call_channel_name = f"{zone_base}-heat-call"

    # DerivedChannelGt.AsyncEmitDelta: int, hundredths °F (consistent with GwUnit.FahrenheitX100).
    async_emit_delta_x100 = max(1, int(round(async_emit_delta_f * 100)))

    db.add_derived_channels(
        [
            DerivedChannelGt(
                Id=db.make_derived_channel_id(f"{zone_base}-pred-setpoint"),
                Name=f"{zone_base}-pred-setpoint",
                CreatedByNodeName=H0N.derived_generator,
                Strategy="predicted-setpoint",
                InputChannelNames=[gw_temp_channel_name],
                OutputUnit=GwUnit.FahrenheitX100,
                EmissionMethod=EmissionMethod.AsyncAndPeriodic,
                AsyncEmitDelta=async_emit_delta_x100,
                EmitPeriodS=emit_period_s,
                Parameters={
                    "HeatCallChannelName": heat_call_channel_name,
                    "SetpointThresholdF": threshold_f,
                },
                DisplayName=(
                    f"Zone {zone_idx} {zone_name.replace('-', ' ').title()} "
                    "Predicted Setpoint"
                ),
                TerminalAssetAlias=db.terminal_asset_alias,
            )
        ]
    )


def add_zone_predicted_setpoint_channels(
    db: LayoutDb,
    *,
    zone_names: Sequence[str] | dict[int, str] | None = None,
    gw_temp_channel_names: dict[int, str] | None = None,
    heat_call_channel_names: dict[int, str] | None = None,
    threshold_f: float = 2.0,
    async_emit_delta_f: float = 0.2,
    emit_period_s: int = 300,
) -> None:
    """Add zone{x}-{zone-name}-pred-setpoint channels from zone gw-temp readings."""
    gw_temp_channel_names = gw_temp_channel_names or {}
    heat_call_channel_names = heat_call_channel_names or {}

    for zone_idx, zone_name in _zone_items(db, zone_names):
        _add_zone_predicted_setpoint_channel(
            db,
            zone_idx=zone_idx,
            zone_name=zone_name,
            gw_temp_channel_name=gw_temp_channel_names.get(zone_idx),
            heat_call_channel_name=heat_call_channel_names.get(zone_idx),
            threshold_f=threshold_f,
            async_emit_delta_f=async_emit_delta_f,
            emit_period_s=emit_period_s,
        )
