"""Tests gt.dispatch.boolean.local.100 type"""
import json

import pytest
from schema.errors import MpSchemaError
from schema.messages import GtDispatchBooleanLocal_Maker as Maker


def test_gt_dispatch_boolean_local():

    gw_dict = {
        "SendTimeUnixMs": 1657025211851,
        "FromNodeAlias": "a.s",
        "AboutNodeAlias": "a.elt1.relay",
        "RelayState": 1,
        "TypeAlias": "gt.dispatch.boolean.local.100",
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
        send_time_unix_ms=gw_tuple.SendTimeUnixMs,
        from_node_alias=gw_tuple.FromNodeAlias,
        about_node_alias=gw_tuple.AboutNodeAlias,
        relay_state=gw_tuple.RelayState,
        #
    ).tuple
    assert t == gw_tuple

    ######################################
    # MpSchemaError raised if missing a required attribute
    ######################################

    orig_value = gw_dict["TypeAlias"]
    del gw_dict["TypeAlias"]
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["TypeAlias"] = orig_value

    orig_value = gw_dict["SendTimeUnixMs"]
    del gw_dict["SendTimeUnixMs"]
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["SendTimeUnixMs"] = orig_value

    orig_value = gw_dict["FromNodeAlias"]
    del gw_dict["FromNodeAlias"]
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["FromNodeAlias"] = orig_value

    orig_value = gw_dict["AboutNodeAlias"]
    del gw_dict["AboutNodeAlias"]
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["AboutNodeAlias"] = orig_value

    orig_value = gw_dict["RelayState"]
    del gw_dict["RelayState"]
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["RelayState"] = orig_value

    ######################################
    # MpSchemaError raised if attributes have incorrect type
    ######################################

    orig_value = gw_dict["SendTimeUnixMs"]
    gw_dict["SendTimeUnixMs"] = 1.1
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["SendTimeUnixMs"] = orig_value

    orig_value = gw_dict["FromNodeAlias"]
    gw_dict["FromNodeAlias"] = 42
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["FromNodeAlias"] = orig_value

    orig_value = gw_dict["AboutNodeAlias"]
    gw_dict["AboutNodeAlias"] = 42
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["AboutNodeAlias"] = orig_value

    orig_value = gw_dict["RelayState"]
    gw_dict["RelayState"] = 1.1
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["RelayState"] = orig_value

    ######################################
    # MpSchemaError raised if TypeAlias is incorrect
    ######################################

    gw_dict["TypeAlias"] = "not the type alias"
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["TypeAlias"] = "gt.dispatch.boolean.local.100"

    ######################################
    # MpSchemaError raised if primitive attributes do not have appropriate property_format
    ######################################

    gw_dict["SendTimeUnixMs"] = 1656245000
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["SendTimeUnixMs"] = 1657025211851

    gw_dict["FromNodeAlias"] = "a.b-h"
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["FromNodeAlias"] = "a.s"

    gw_dict["AboutNodeAlias"] = "a.b-h"
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["AboutNodeAlias"] = "a.elt1.relay"

    gw_dict["RelayState"] = 2
    with pytest.raises(MpSchemaError):
        Maker.dict_to_tuple(gw_dict)
    gw_dict["RelayState"] = 1

    # End of Test
