from pydantic import BaseModel
from gwsproto.property_format import SpaceheatName
from gwsproto.enums import TempCalcMethod

class TankCfg(BaseModel):
    SerialNumber: str
    PicoHwUid: str
    ActorNodeName: SpaceheatName
    CapturePeriodS: int = 60
    AsyncCaptureDeltaMicroVolts: int = 2000
    Samples:int  = 1000
    NumSampleAverages:int = 30
    Enabled: bool = True
    SendMicroVolts: bool = True
    TempCalc: TempCalcMethod = TempCalcMethod.SimpleBeta
    ThermistorBeta: int = 3977 # Beta for the Amphenols
    SensorOrder: list[int] | None = None
    
    def component_display_name(self) -> str:
        return f"{self.ActorNodeName} TankModule"
