from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import TelemetryName
from sema_snapshot.sema.property_format import NonNegativeInt
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.types.i2c_bus import I2cBus
from sema_snapshot.sema.types.i2c_ct_interface_capability import (
    I2cCtInterfaceCapability,
)
from sema_snapshot.sema.types.i2c_dac_capability import I2cDacCapability
from sema_snapshot.sema.types.i2c_expander import I2cExpander
from sema_snapshot.sema.types.i2c_mux import I2cMux
from sema_snapshot.sema.types.i2c_relay_capability import I2cRelayCapability
from sema_snapshot.sema.types.i2c_thermistor_interface_capability import (
    I2cThermistorInterfaceCapability,
)
from sema_snapshot.sema.types.native_gpio_pin import NativeGpioPin


class ScadaDeviceTypeGt(SemaType):
    """Sema: https://schemas.electricity.works/types/gw1.scada.device.type.gt/000"""

    device_type: PascalCase
    display_name: str | None = None
    min_poll_period_ms: PositiveInt | None = None
    bus_list: list[I2cBus]
    telemetry_name_list: list[TelemetryName]
    native_gpio_inputs: list[NativeGpioPin]
    native_gpio_outputs: list[NativeGpioPin]
    expanders: list[I2cExpander]
    muxes: list[I2cMux]
    i2c_relays: list[I2cRelayCapability]
    supports_pin_readback: bool
    relay_energized_level: NonNegativeInt
    ct_adc: I2cCtInterfaceCapability | None = None
    thermistor_adcs: list[I2cThermistorInterfaceCapability]
    dacs: list[I2cDacCapability]
    type_name: Literal["gw1.scada.device.type.gt"] = "gw1.scada.device.type.gt"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "ScadaDeviceTypeGt":
        """
        Axiom 1: BusMembership
        Every I2cBus referenced by an entry in Expanders, Muxes, CtAdc,
        ThermistorAdcs, or Dacs SHALL appear as a Name in BusList.
        """
        bus_names = {bus.name for bus in (self.bus_list or [])}
        referenced = [expander.i2c_bus for expander in (self.expanders or [])]
        referenced += [mux.i2c_bus for mux in (self.muxes or [])]
        referenced += [adc.i2c_bus for adc in (self.thermistor_adcs or [])]
        referenced += [dac.i2c_bus for dac in (self.dacs or [])]
        if self.ct_adc is not None:
            referenced.append(self.ct_adc.i2c_bus)
        missing = sorted({bus for bus in referenced if bus not in bus_names})
        if missing:
            raise ValueError(
                "Axiom 1 (BusMembership) failed: I2cBus value(s) "
                f"{missing} are not declared in BusList."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "ScadaDeviceTypeGt":
        """
        Axiom 2: ExpanderMembership
        Every ExpanderIdx referenced by an entry in I2cRelays SHALL appear as an
        ExpanderIdx in Expanders.
        """
        expander_idxs = {e.expander_idx for e in (self.expanders or [])}
        missing = sorted(
            {
                relay.expander_idx
                for relay in (self.i2c_relays or [])
                if relay.expander_idx not in expander_idxs
            }
        )
        if missing:
            raise ValueError(
                "Axiom 2 (ExpanderMembership) failed: ExpanderIdx value(s) "
                f"{missing} are not declared in Expanders."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "ScadaDeviceTypeGt":
        """
        Axiom 3: BoardIdentifierUniqueness
        The board's silk-screen namespace is one namespace: the union of every
        RelayName in I2cRelays, the CtAdc Name, every Name in ThermistorAdcs,
        every DacName in Dacs, every MuxName in Muxes, and every Name in
        NativeGpioInputs and NativeGpioOutputs SHALL contain no duplicates
        within the record.
        """
        names = [r.relay_name for r in (self.i2c_relays or [])]
        if self.ct_adc is not None:
            names.append(self.ct_adc.name)
        names += [a.name for a in (self.thermistor_adcs or [])]
        names += [d.dac_name for d in (self.dacs or [])]
        names += [m.mux_name for m in (self.muxes or [])]
        names += [p.name for p in (self.native_gpio_inputs or [])]
        names += [p.name for p in (self.native_gpio_outputs or [])]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(
                "Axiom 3 (BoardIdentifierUniqueness) failed: duplicate board "
                f"identifier name(s) {dupes}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> "ScadaDeviceTypeGt":
        """
        Axiom 4: MuxConsistency
        a. Every MuxName referenced by an entry in Dacs SHALL appear as a
        MuxName in Muxes.
        b. Every Dacs entry carrying MuxChannel SHALL satisfy MuxChannel less
        than the Channels of the mux named by its MuxName.
        c. Every Dacs entry carrying MuxName SHALL have an I2cBus equal to
        that mux's I2cBus.
        """
        muxes = {m.mux_name: m for m in (self.muxes or [])}
        for dac in self.dacs or []:
            if dac.mux_name is None:
                continue
            mux = muxes.get(dac.mux_name)
            if mux is None:
                raise ValueError(
                    "Axiom 4 (MuxConsistency, clause a) failed: Dacs entry "
                    f"{dac.dac_name} references MuxName {dac.mux_name}, "
                    "which is not declared in Muxes."
                )
            if dac.mux_channel is not None and dac.mux_channel >= mux.channels:
                raise ValueError(
                    "Axiom 4 (MuxConsistency, clause b) failed: Dacs entry "
                    f"{dac.dac_name} has MuxChannel {dac.mux_channel}, not "
                    f"less than the {mux.channels} Channels of mux "
                    f"{dac.mux_name}."
                )
            if dac.i2c_bus != mux.i2c_bus:
                raise ValueError(
                    "Axiom 4 (MuxConsistency, clause c) failed: Dacs entry "
                    f"{dac.dac_name} has I2cBus {dac.i2c_bus} but its mux "
                    f"{dac.mux_name} is on {mux.i2c_bus}."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> "ScadaDeviceTypeGt":
        """
        Axiom 5: RelayEnergizedLevelRange
        RelayEnergizedLevel SHALL be 0 or 1.
        """
        if self.relay_energized_level not in (0, 1):
            raise ValueError(
                "Axiom 5 (RelayEnergizedLevelRange) failed: RelayEnergizedLevel "
                f"{self.relay_energized_level} must be 0 or 1."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_6(self) -> "ScadaDeviceTypeGt":
        """
        Axiom 6: SingleBus
        BusList SHALL have exactly one entry: a scada process drives one bus,
        and the bus actor opens that entry's adapter. (Retired by the
        multi-bus work, which replaces this axiom with per-bus binding.)
        """
        if len(self.bus_list) != 1:
            raise ValueError(
                "Axiom 6 (SingleBus) failed: BusList declares "
                f"{len(self.bus_list)} buses; exactly one is required."
            )
        return self
