"""Tests data.channel.gt type, version 002"""

import pytest

from gwsproto.named_types import DataChannelGt


def test_data_channel_gt_generated() -> None:
    d = {
        "Name": "dist-pump-pwr",
        "DisplayName": "Dist Pump Pwr",
        "AboutNodeName": "dist-pump",
        "CapturedByNodeName": "power-meter",
        "TelemetryName": "PowerW",
        "Quantity": "Power",
        "TerminalAssetAlias": "hw1.isone.me.versant.keene.spruce.ta",
        "Id": "b0ab5bc7-7b9f-4ed2-8e93-1f8ca5f5f2d0",
        "TypeName": "data.channel.gt",
        "Version": "002",
    }

    d2 = DataChannelGt.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d


def test_data_channel_gt_axiom_1() -> None:
    d = {
        "Name": "dist-pump-pwr",
        "DisplayName": "Dist Pump Pwr",
        "AboutNodeName": "dist-pump",
        "CapturedByNodeName": "power-meter",
        "TelemetryName": "GpmTimes100",
        "Quantity": "FlowRate",
        "TerminalAssetAlias": "hw1.isone.me.versant.keene.spruce.ta",
        "InPowerMetering": True,
        "Id": "b0ab5bc7-7b9f-4ed2-8e93-1f8ca5f5f2d0",
        "TypeName": "data.channel.gt",
        "Version": "002",
    }

    with pytest.raises(ValueError, match="Axiom 1 violated!"):
        DataChannelGt.model_validate(d)


def test_data_channel_gt_axiom_2() -> None:
    d = {
        "Name": "dist-pump-pwr",
        "DisplayName": "Dist Pump Pwr",
        "AboutNodeName": "dist-pump",
        "CapturedByNodeName": "power-meter",
        "TelemetryName": "PowerW",
        "Quantity": "Temperature",
        "TerminalAssetAlias": "hw1.isone.me.versant.keene.spruce.ta",
        "Id": "b0ab5bc7-7b9f-4ed2-8e93-1f8ca5f5f2d0",
        "TypeName": "data.channel.gt",
        "Version": "002",
    }

    with pytest.raises(ValueError, match="Axiom 2 violated!"):
        DataChannelGt.model_validate(d)
