"""The BoardResolution axiom body the layout words share."""

from typing import Any, Iterable, NamedTuple

from gwsproto.named_types.scada_device_type_gt import ScadaDeviceTypeGt


class BoardNameKind(NamedTuple):
    """Where a board-resident component kind names its place on the board:
    the component field holding the name, the board record's capability list,
    and the field of that list's entries the name is matched against."""

    component_field: str
    record_list: str
    entry_field: str


GPIO_SENSOR = BoardNameKind("GpioName", "NativeGpioInputs", "Name")
GPIO_RELAY = BoardNameKind("GpioName", "NativeGpioOutputs", "Name")
I2C_THERMISTOR_READER = BoardNameKind("AdcName", "ThermistorAdcs", "Name")
I2C_RELAY = BoardNameKind("RelayName", "I2cRelays", "RelayName")
I2C_DAC_OUTPUT = BoardNameKind("DacName", "Dacs", "DacName")


def check_board_resolution(
    components: Iterable[Any],
    device_types: Iterable[Any],
    kinds: dict[str, BoardNameKind],
    label: str,
    *,
    every_board_resident: bool,
) -> None:
    """Each board-resident component resolves through its board component to a
    name in the board's gw1.scada.device.type.gt record. With
    `every_board_resident`, any component carrying a BoardComponentId is held
    to the board and record steps; otherwise only the kinds listed are."""
    components = list(components)
    boards = {
        c.ComponentId: c
        for c in components
        if c.TypeName == "scada.board.component.gt"
    }
    records = {
        r.DeviceType: r for r in device_types if isinstance(r, ScadaDeviceTypeGt)
    }
    for c in components:
        kind = kinds.get(c.TypeName)
        board_id = getattr(c, "BoardComponentId", None)
        if kind is None and not (every_board_resident and board_id is not None):
            continue
        board = boards.get(board_id)
        if board is None:
            raise ValueError(
                f"{label} failed: BoardComponentId '{board_id}' of component "
                f"'{c.ComponentId}' does not resolve to a scada.board.component.gt."
            )
        record = records.get(board.DeviceType)
        if record is None:
            raise ValueError(
                f"{label} failed: board DeviceType '{board.DeviceType}' has no "
                "gw1.scada.device.type.gt record."
            )
        if kind is None:
            continue
        names = {
            getattr(e, kind.entry_field) for e in getattr(record, kind.record_list)
        }
        wanted = getattr(c, kind.component_field)
        if wanted not in names:
            raise ValueError(
                f"{label} failed: name '{wanted}' of component '{c.ComponentId}' "
                f"is not in the board record's {kind.record_list}."
            )
