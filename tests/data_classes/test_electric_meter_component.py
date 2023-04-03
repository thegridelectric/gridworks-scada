from actors.config import ScadaSettings
from data_classes.components.electric_meter_component import ElectricMeterComponent
from data_classes.hardware_layout import HardwareLayout
from schema.electric_meter_component_gt import ElectricMeterComponentGt_Maker


def test_electric_meter_component():
    settings = ScadaSettings()
    HardwareLayout.load(settings.paths.hardware_layout)
    d = {
      "ComponentId":"2bfd0036-0b0e-4732-8790-bc7d0536a85e",
      "ComponentAttributeClassId":"28897ac1-ea42-4633-96d3-196f63f5a951",
      "DisplayName":"Power Meter for Simulated Test system",
      "ConfigList":[
         {
            "AboutNodeName":"a.elt1",
            "ReportOnChange":True,
            "SamplePeriodS":300,
            "Exponent":0,
            "AsyncReportThreshold":0.02,
            "NameplateMaxValue":4500,
            "TypeName":"telemetry.reporting.config",
            "Version":"000",
            "TelemetryNameGtEnumSymbol":"af39eec9",
            "UnitGtEnumSymbol":"f459a9c3"
         },
         {
            "AboutNodeName":"a.elt2",
            "ReportOnChange":True,
            "SamplePeriodS":300,
            "Exponent":0,
            "AsyncReportThreshold":0.02,
            "NameplateMaxValue":4500,
            "TypeName":"telemetry.reporting.config",
            "Version":"000",
            "TelemetryNameGtEnumSymbol":"af39eec9",
            "UnitGtEnumSymbol":"f459a9c3"
         }
      ],
      "HwUid":"9999",
      "EgaugeIoList":[

      ],
      "TypeName":"electric.meter.component.gt",
      "Version":"000"
   }

    gw_tuple = ElectricMeterComponentGt_Maker.dict_to_tuple(d)
    assert gw_tuple.ComponentId in ElectricMeterComponent.by_id.keys()
    component_as_dc = ElectricMeterComponent.by_id[gw_tuple.ComponentId]
    assert gw_tuple.HwUid == "9999"
    assert component_as_dc.hw_uid == "35941_308"
