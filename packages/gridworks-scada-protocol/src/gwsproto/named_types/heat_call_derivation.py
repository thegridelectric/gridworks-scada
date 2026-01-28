from typing import Literal
from typing_extensions import Self
from pydantic import BaseModel,  model_validator

from gwsproto.enums import HeatCallInterpretation
from gwsproto.property_format import SpaceheatName

class HeatCallDerivation(BaseModel):
    SourceChannelName: SpaceheatName
    DerivedChannelName: SpaceheatName
    Interpretation: HeatCallInterpretation
    Threshold: int | None = None

    TypeName: Literal["gw1.heat.call.derivation"] = "gw1.heat.call.derivation"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Threshold exists iff HeatCallInterpretation is GreaterThanThreshold
        """
        has_threshold = self.Threshold is not None
        needs_threshold = self.Interpretation == HeatCallInterpretation.GreaterThanThreshold
        if has_threshold != needs_threshold:
            if self.Interpretation != HeatCallInterpretation.GreaterThanThreshold:

                raise ValueError(
                    "Axiom 1: Threshold exists iff HeatCallInterpretation is GreaterThanThreshold"
                )
        return self
