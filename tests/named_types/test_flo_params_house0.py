"""Tests flo.params.house0 type, version 000"""

from gwsproto.enums import MarketPriceUnit
from gwsproto.named_types import FloParamsHouse0


def test_flo_params_house0_generated() -> None:
    ...
    # d = {
    #     "GNodeAlias": "d1.isone.ver.keene.holly",
    #     "FloParamsUid": "97eba574-bd20-45b5-bf82-9ba2f492d8f6",
    #     "TimezoneStr": ,
    #     "StartUnixS": 1734476700,
    #     "HorizonHours": ,
    #     "StorageVolumeGallons": ,
    #     "StorageLossesPercent": ,
    #     "HpMinElecKw": ,
    #     "HpMaxElecKw": ,
    #     "CopIntercept": ,
    #     "CopOatCoeff": ,
    #     "CopLwtCoeff": ,
    #     "InitialTopTempF": ,
    #     "InitialBottomTempF",
    #     "InitialThermocline": ,
    #     "LmpForecast": ,
    #     "DistPriceForecast": ,
    #     "RegPriceForecast": ,
    #     "PriceForecastUid": ,
    #     "OatForecastF": ,
    #     "WindSpeedForecastMph": ,
    #     "WeatherUid": ,
    #     "AlphaTimes10": ,
    #     "BetaTimes100": ,
    #     "GammaEx6": ,
    #     "IntermediatePowerKw": ,
    #     "IntermediateRswtF": ,
    #     "DdPowerKw": ,
    #     "DdRswtF": ,
    #     "DdDeltaTF": ,
    #     "MaxEwtF": ,
    #     "MarketPriceUnit": "",
    #     "ParamsGeneratedS": ,
    #     "TypeName": "flo.params.house0",
    #     "Version": "002",
    # }

    # d2 = FloParamsHouse0.model_validate(d).model_dump(exclude_none=True)

    # assert d2 == d

    # ######################################
    # # Enum related
    # ######################################

    # assert type(d2["MarketPriceUnit"]) is str

    # d2 = dict(d, MarketPriceUnit="unknown_enum_thing")
    # assert FloParamsHouse0(**d2).MarketPriceUnit == MarketPriceUnit.default()
