from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import EmissionMethod, GwUnit, HeatCallInterpretation
from gwsproto.names.hydronic_spaceheat.channel_names import (
    HydronicSpaceheatZoneChannelNames as HSZoneChannelNames,
)
from gwsproto.names.nolan.channel_names import NolanZoneChannelNames
from layout_gen.layout_db import LayoutDb
from gwsproto.named_types import DerivedChannelGt

NOLAN_LAYOUT_STRATEGY = "Nolan"


def _check_nolan_layout(db: LayoutDb) -> None:
    strategy = db.misc.get("Strategy", db.loaded.strategy)
    if strategy != NOLAN_LAYOUT_STRATEGY:
        raise ValueError(
            "Nolan zone derived channels require LayoutDb misc Strategy "
            f"'{NOLAN_LAYOUT_STRATEGY}', got {strategy!r}"
        )


def _zone_items(db: LayoutDb) -> list[tuple[int, str]]:
    _check_nolan_layout(db)

    zone_names = db.misc.get("ZoneList", db.loaded.zone_list)
    if not zone_names:
        raise ValueError(
            "Nolan layouts must have zone names in LayoutDb misc ZoneList"
        )

    return list(enumerate(zone_names, start=1))


def _has_data_channel(db: LayoutDb, channel_name: str) -> bool:
    return channel_name in db.maps.channels_by_name


def _add_zone_heat_call_channel(
    db: LayoutDb,
    *,
    zone_idx: int,
    zone_name: str,
    threshold: float | None = None,
    emit_period_s: int = 300,
) -> None:
    _check_nolan_layout(db)

    zone_channels = HSZoneChannelNames(zone_name, zone_idx)
    nolan_channels = NolanZoneChannelNames(zone_name, zone_idx)

    params: dict[str, str | float] = {
        "Interpretation": HeatCallInterpretation.DigitalZeroIsActive.value
    }
    if threshold is not None:
        params["Threshold"] = threshold

    db.add_derived_channels(
        [
            DerivedChannelGt(
                Id=db.make_derived_channel_id(zone_channels.heat_call),
                Name=zone_channels.heat_call,
                CreatedByNodeName=H0N.derived_generator,
                Strategy="heat-call",
                InputChannelNames=[nolan_channels.opto_input],
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
    threshold: float | None = None,
    emit_period_s: int = 300,
) -> None:
    """Add zone{x}-{zone-name}-heat-call channels from zone opto inputs."""
    _check_nolan_layout(db)

    for zone_idx, zone_name in _zone_items(db):
        zone_channels = NolanZoneChannelNames(zone_name, zone_idx)
        if not _has_data_channel(db, zone_channels.opto_input):
            continue
        _add_zone_heat_call_channel(
            db,
            zone_idx=zone_idx,
            zone_name=zone_name,
            threshold=threshold,
            emit_period_s=emit_period_s,
        )


def _add_zone_predicted_setpoint_channel(
    db: LayoutDb,
    *,
    zone_idx: int,
    zone_name: str,
    threshold_f: float = 2.0,
    async_emit_delta_f: float = 0.2,
    emit_period_s: int = 300,
) -> None:
    _check_nolan_layout(db)

    zone_channels = HSZoneChannelNames(zone_name, zone_idx)
    nolan_channels = NolanZoneChannelNames(zone_name, zone_idx)

    # AsyncEmitDelta and SetpointThresholdFX100: int, hundredths °F (consistent
    # with GwUnit.FahrenheitX100).
    async_emit_delta_x100 = max(1, int(round(async_emit_delta_f * 100)))
    setpoint_threshold_fx100 = max(1, int(round(threshold_f * 100)))

    db.add_derived_channels(
        [
            DerivedChannelGt(
                Id=db.make_derived_channel_id(zone_channels.set),
                Name=zone_channels.set,
                CreatedByNodeName=H0N.derived_generator,
                Strategy="predicted-setpoint",
                InputChannelNames=[nolan_channels.gw_temp],
                OutputUnit=GwUnit.FahrenheitX100,
                EmissionMethod=EmissionMethod.AsyncAndPeriodic,
                AsyncEmitDelta=async_emit_delta_x100,
                EmitPeriodS=emit_period_s,
                Parameters={
                    "HeatCallChannelName": zone_channels.heat_call,
                    "SetpointThresholdFX100": setpoint_threshold_fx100,
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
    threshold_f: float = 2.0,
    async_emit_delta_f: float = 0.2,
    emit_period_s: int = 300,
) -> None:
    """Add zone{x}-{zone-name}-set channels from zone gw-temp readings."""
    _check_nolan_layout(db)

    for zone_idx, zone_name in _zone_items(db):
        zone_channels = NolanZoneChannelNames(zone_name, zone_idx)
        if not _has_data_channel(db, zone_channels.gw_temp):
            continue
        _add_zone_predicted_setpoint_channel(
            db,
            zone_idx=zone_idx,
            zone_name=zone_name,
            threshold_f=threshold_f,
            async_emit_delta_f=async_emit_delta_f,
            emit_period_s=emit_period_s,
        )
