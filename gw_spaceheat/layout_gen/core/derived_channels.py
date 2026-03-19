from gwsproto.enums import GwUnit, GwQuantity, EmissionMethod
from gwsproto.named_types import DerivedChannelGt, LinearOneDimensionalCalibration
from gwsproto.property_format import SpaceheatName
from layout_gen.core.layout_db import LayoutDb


def add_temperature_channel(
    db: LayoutDb,
    *,
    node_name: SpaceheatName,
    channel_name: SpaceheatName,
    input_channel: SpaceheatName,
    calibration: LinearOneDimensionalCalibration | None = None,
):

    strategy = "identity"
    parameters = None

    if calibration is not None:
        if not (calibration.M == 1 and calibration.B == 0):
            strategy = "affine"
            parameters = {
                "Calibration": calibration.model_dump(exclude_none=True)
            }

    db.add_derived_channels([
        DerivedChannelGt(
            Id=db.make_derived_channel_id(channel_name),
            Name=channel_name,
            CreatedByNodeName=node_name,
            InputChannelNames=[input_channel],
            OutputUnit=GwUnit.FahrenheitX100,
            OutputQuantity=GwQuantity.Temperature,
            Strategy=strategy,
            EmissionMethod=EmissionMethod.OnTrigger,
            Parameters=parameters,
            DisplayName=channel_name.replace("-", " ").title(),
            TerminalAssetAlias=db.terminal_asset_alias,
        )
    ])
