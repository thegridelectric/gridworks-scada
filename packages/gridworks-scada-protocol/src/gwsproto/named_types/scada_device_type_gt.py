from typing import Literal, Optional

from pydantic import BaseModel, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import TelemetryName
from gwsproto.named_types.i2c_ct_interface_capability import I2cCtInterfaceCapability
from gwsproto.named_types.i2c_bus import I2cBus
from gwsproto.named_types.i2c_dac_capability import I2cDacCapability
from gwsproto.named_types.i2c_expander import I2cExpander
from gwsproto.named_types.i2c_mux import I2cMux
from gwsproto.named_types.i2c_relay_capability import I2cRelayCapability
from gwsproto.named_types.i2c_thermistor_interface_capability import (
    I2cThermistorInterfaceCapability,
)
from gwsproto.named_types.native_gpio_pin import NativeGpioPin
from gwsproto.property_format import PascalCase


class ScadaDeviceTypeGt(BaseModel):
    """Sema: https://schemas.electricity.works/types/gw1.scada.device.type.gt/000"""

    DeviceType: PascalCase
    DisplayName: Optional[str] = None
    MinPollPeriodMs: Optional[PositiveInt] = None
    BusList: list[I2cBus] = []
    TelemetryNameList: list[TelemetryName] = []
    NativeGpioInputs: list[NativeGpioPin] = []
    NativeGpioOutputs: list[NativeGpioPin] = []
    Expanders: list[I2cExpander] = []
    Muxes: list[I2cMux] = []
    I2cRelays: list[I2cRelayCapability] = []
    CtAdc: Optional[I2cCtInterfaceCapability] = None
    ThermistorAdcs: list[I2cThermistorInterfaceCapability] = []
    Dacs: list[I2cDacCapability] = []
    TypeName: Literal["gw1.scada.device.type.gt"] = "gw1.scada.device.type.gt"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: BusMembership. Every I2cBus referenced by an entry in Expanders,
        Muxes, CtAdc, ThermistorAdcs, or Dacs SHALL appear as a Name in BusList.
        """
        bus_names = {bus.Name for bus in self.BusList}
        referenced: set[str] = {expander.I2cBus for expander in self.Expanders}
        referenced |= {mux.I2cBus for mux in self.Muxes}
        referenced |= {ta.I2cBus for ta in self.ThermistorAdcs}
        referenced |= {dac.I2cBus for dac in self.Dacs}
        if self.CtAdc is not None:
            referenced.add(self.CtAdc.I2cBus)
        missing = referenced - bus_names
        if missing:
            raise ValueError(
                f"Axiom 1 (BusMembership) failed: I2cBus name(s) {sorted(missing)} "
                f"not in BusList {sorted(bus_names)}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: ExpanderMembership. Every ExpanderIdx referenced by an entry in
        I2cRelays SHALL appear as an ExpanderIdx in Expanders.
        """
        expander_idxs = {e.ExpanderIdx for e in self.Expanders}
        missing = sorted(
            {
                relay.ExpanderIdx
                for relay in self.I2cRelays
                if relay.ExpanderIdx not in expander_idxs
            }
        )
        if missing:
            raise ValueError(
                f"Axiom 2 (ExpanderMembership) failed: ExpanderIdx value(s) "
                f"{missing} are not declared in Expanders."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: BoardIdentifierUniqueness.
        The board's silk-screen namespace is one namespace: the union of every
        RelayName in I2cRelays, the CtAdc Name, every Name in ThermistorAdcs,
        every DacName in Dacs, every MuxName in Muxes, and every Name in
        NativeGpioInputs and NativeGpioOutputs SHALL contain no duplicates
        within the record.
        """
        names = [r.RelayName for r in (self.I2cRelays or [])]
        if self.CtAdc is not None:
            names.append(self.CtAdc.Name)
        names += [a.Name for a in (self.ThermistorAdcs or [])]
        names += [d.DacName for d in (self.Dacs or [])]
        names += [m.MuxName for m in (self.Muxes or [])]
        names += [p.Name for p in (self.NativeGpioInputs or [])]
        names += [p.Name for p in (self.NativeGpioOutputs or [])]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(
                "Axiom 3 (BoardIdentifierUniqueness) failed: duplicate board "
                f"identifier name(s) {dupes}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: MuxConsistency.
        a. Every MuxName referenced by an entry in Dacs SHALL appear as a
        MuxName in Muxes. b. Every Dacs entry carrying MuxChannel SHALL satisfy
        MuxChannel less than the Channels of the mux named by its MuxName.
        c. Every Dacs entry carrying MuxName SHALL have an I2cBus equal to
        that mux's I2cBus.
        """
        muxes = {m.MuxName: m for m in self.Muxes}
        for dac in self.Dacs:
            if dac.MuxName is None:
                continue
            mux = muxes.get(dac.MuxName)
            if mux is None:
                raise ValueError(
                    "Axiom 4 (MuxConsistency) failed: Dacs entry "
                    f"{dac.DacName} references MuxName {dac.MuxName}, "
                    "which is not declared in Muxes."
                )
            if dac.MuxChannel is not None and dac.MuxChannel >= mux.Channels:
                raise ValueError(
                    "Axiom 4 (MuxConsistency) failed: Dacs entry "
                    f"{dac.DacName} has MuxChannel {dac.MuxChannel}, not "
                    f"less than the {mux.Channels} Channels of mux "
                    f"{dac.MuxName}."
                )
            if dac.I2cBus != mux.I2cBus:
                raise ValueError(
                    "Axiom 4 (MuxConsistency) failed: Dacs entry "
                    f"{dac.DacName} has I2cBus {dac.I2cBus} but its mux "
                    f"{dac.MuxName} is on {mux.I2cBus}."
                )
        return self
