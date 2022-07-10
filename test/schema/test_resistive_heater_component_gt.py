"""Tests resistive.heater.component.gt.100 type"""
import json

import pytest

from schema.errors import MpSchemaError
from schema.gt.resistive_heater_component_gt.resistive_heater_component_gt_maker import (
    ResistiveHeaterComponentGt_Maker as Maker,
)


def test_resistive_heater_component_gt():

    gw_dict = {
        "DisplayName": "First 4.5 kW boost in tank",
        "TestedMaxHotMilliOhms": 13714,
        "HwUid": "aaaa2222",
        "ComponentId": "80f95280-e999-49e0-a0e4-a7faf3b5b3bd",
        "TestedMaxColdMilliOhms": 14500,
        "ComponentAttributeClassId": "cf1f2587-7462-4701-b962-d2b264744c1d",
        "TypeAlias": "resistive.heater.component.gt.100",
    }

    with pytest.raises(MpSchemaError):
        Maker.type_to_tuple(gw_dict)

    with pytest.raises(MpSchemaError):
        Maker.type_to_tuple('"not a dict"')

    # Test type_to_tuple
    gw_type = json.dumps(gw_dict)
    gw_tuple = Maker.type_to_tuple(gw_type)

    # test type_to_tuple and tuple_to_type maps
    assert Maker.type_to_tuple(Maker.tuple_to_type(gw_tuple)) == gw_tuple

    # test Maker init
    t = Maker(
        display_name=gw_tuple.DisplayName,
        tested_max_hot_milli_ohms=gw_tuple.TestedMaxHotMilliOhms,
        component_attribute_class_id=gw_tuple.ComponentAttributeClassId,
        hw_uid=gw_tuple.HwUid,
        component_id=gw_tuple.ComponentId,
        tested_max_cold_milli_ohms=gw_tuple.TestedMaxColdMilliOhms,
        #
    ).tuple
    assert t == gw_tuple

    ######################################
    # Dataclass related tests
    ######################################

    dc = Maker.tuple_to_dc(gw_tuple)
    assert gw_tuple == Maker.dc_to_tuple(dc)
    assert Maker.type_to_dc(Maker.dc_to_type(dc)) == dc

    ######################################
    # MpSchemaError raised if missing a required attribute
    ######################################

    orig_value = gw_dict["TypeAlias"]
    del gw_dict["TypeAlias"]
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["TypeAlias"] = orig_value

    orig_value = gw_dict["ComponentAttributeClassId"]
    del gw_dict["ComponentAttributeClassId"]
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["ComponentAttributeClassId"] = orig_value

    orig_value = gw_dict["ComponentId"]
    del gw_dict["ComponentId"]
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["ComponentId"] = orig_value

    ######################################
    # Optional attributes can be removed from type
    ######################################

    orig_value = gw_dict["DisplayName"]
    del gw_dict["DisplayName"]
    gw_type = json.dumps(gw_dict)
    gw_tuple = Maker.type_to_tuple(gw_type)
    assert Maker.type_to_tuple(Maker.tuple_to_type(gw_tuple)) == gw_tuple
    gw_dict["DisplayName"] = orig_value

    orig_value = gw_dict["TestedMaxHotMilliOhms"]
    del gw_dict["TestedMaxHotMilliOhms"]
    gw_type = json.dumps(gw_dict)
    gw_tuple = Maker.type_to_tuple(gw_type)
    assert Maker.type_to_tuple(Maker.tuple_to_type(gw_tuple)) == gw_tuple
    gw_dict["TestedMaxHotMilliOhms"] = orig_value

    orig_value = gw_dict["HwUid"]
    del gw_dict["HwUid"]
    gw_type = json.dumps(gw_dict)
    gw_tuple = Maker.type_to_tuple(gw_type)
    assert Maker.type_to_tuple(Maker.tuple_to_type(gw_tuple)) == gw_tuple
    gw_dict["HwUid"] = orig_value

    orig_value = gw_dict["TestedMaxColdMilliOhms"]
    del gw_dict["TestedMaxColdMilliOhms"]
    gw_type = json.dumps(gw_dict)
    gw_tuple = Maker.type_to_tuple(gw_type)
    assert Maker.type_to_tuple(Maker.tuple_to_type(gw_tuple)) == gw_tuple
    gw_dict["TestedMaxColdMilliOhms"] = orig_value

    ######################################
    # MpSchemaError raised if attributes have incorrect type
    ######################################

    orig_value = gw_dict["DisplayName"]
    gw_dict["DisplayName"] = 42
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["DisplayName"] = orig_value

    orig_value = gw_dict["TestedMaxHotMilliOhms"]
    gw_dict["TestedMaxHotMilliOhms"] = 1.1
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["TestedMaxHotMilliOhms"] = orig_value

    orig_value = gw_dict["ComponentAttributeClassId"]
    gw_dict["ComponentAttributeClassId"] = "Not a dataclass id"
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["ComponentAttributeClassId"] = orig_value

    orig_value = gw_dict["HwUid"]
    gw_dict["HwUid"] = 42
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["HwUid"] = orig_value

    orig_value = gw_dict["ComponentId"]
    gw_dict["ComponentId"] = 42
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["ComponentId"] = orig_value

    orig_value = gw_dict["TestedMaxColdMilliOhms"]
    gw_dict["TestedMaxColdMilliOhms"] = 1.1
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["TestedMaxColdMilliOhms"] = orig_value

    ######################################
    # MpSchemaError raised if TypeAlias is incorrect
    ######################################

    gw_dict["TypeAlias"] = "not the type alias"
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["TypeAlias"] = "resistive.heater.component.gt.100"

    ######################################
    # MpSchemaError raised if primitive attributes do not have appropriate property_format
    ######################################

    gw_dict["ComponentId"] = "d4be12d5-33ba-4f1f-b9e5"
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["ComponentId"] = "80f95280-e999-49e0-a0e4-a7faf3b5b3bd"

    # End of Test
