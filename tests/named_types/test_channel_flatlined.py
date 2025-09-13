"""Tests channel.flatlined type, version 000"""

from gwsproto.named_types import ChannelFlatlined


def test_channel_flatlined_generated() -> None:
    d = {
        "FromName": "power-meter",
        "Channel": { "Name": "hp-idu-pwr", "DisplayName": "Hp IDU", "AboutNodeName": "hp-idu-pwr", "CapturedByNodeName": "power-meter", "TelemetryName": "PowerW", "TerminalAssetAlias": "hw1.isone.me.versant.keene.beech.ta", "InPowerMetering": True, "StartS": 1721405699, "Id": "50cf426b-ff3f-4a30-8415-8d3fba5e0ab7", "TypeName": "data.channel.gt", "Version": "001", },
        "TypeName": "channel.flatlined",
        "Version": "000",
    }

    d2 = ChannelFlatlined.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
