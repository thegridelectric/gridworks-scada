"""The store temperature pass every reader of tank layers shares: drop
readings that cannot be water, then fill the layers that are missing from
the layer below, so a stratified store always has a full, plausible set to
judge and to plan on."""

MIN_VALID_TANK_TEMP_F = 35
"""Water in a tank is never below freezing plus a margin; a reading under
this is a sensor fault, not a cold store (a summer store at basement
ambient reads about 60 F)."""
MAX_VALID_TANK_TEMP_F = 200


def valid_tank_temp(value: float | None) -> bool:
    return value is not None and MIN_VALID_TANK_TEMP_F <= value <= MAX_VALID_TANK_TEMP_F


def scrub_and_fill_store_temps(
    temps: dict[str, float], store_layers: list[str], cold_pipe: str
) -> None:
    """In place. `store_layers` runs top to bottom (tank1 depth1 first,
    last tank depth3 last). Every store layer outside the valid range is
    dropped; each missing layer then takes the value of the layer below
    it. The bottom-most missing layer takes the store cold pipe when it
    reports a valid value, else the coldest reporting layer. With no layer
    reporting, nothing is filled, cold pipe or not: a store with no data
    stays a store with no data."""
    for layer in store_layers:
        if layer in temps and not valid_tank_temp(temps[layer]):
            del temps[layer]
    reporting = [temps[layer] for layer in store_layers if layer in temps]
    if not reporting:
        return
    if valid_tank_temp(temps.get(cold_pipe)):
        value_below = temps[cold_pipe]
    else:
        value_below = min(reporting)
    for layer in reversed(store_layers):
        if layer not in temps:
            temps[layer] = value_below
        value_below = temps[layer]
