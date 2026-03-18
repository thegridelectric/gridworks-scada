from pydantic import BaseModel
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import GwUnit, GwQuantity, EmissionMethod
from gwsproto.named_types import DerivedChannelGt, LinearOneDimensionalCalibration
from layout_gen.core.layout_db import LayoutDb


class AffineTempCal(BaseModel):
    """ first term unitless (m), second term integer (output units)"""
    depth1: tuple[float, int] = (1.0, 0)
    depth2: tuple[float, int] = (1.0, 0)
    depth3: tuple[float, int] = (1.0, 0)

    def calibration_for_depth(self, depth: int) -> LinearOneDimensionalCalibration:
        m, b = getattr(self, f"depth{depth}")
        return LinearOneDimensionalCalibration(
            M=m,
            B=b,
        )

def add_temperature_channel(
    db,
    *,
    node_name: str,
    channel_name: str,
    input_channel: str,
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


def add_house0_effective_temp_channels(
    *,
    db: LayoutDb,
    buffer_cal: AffineTempCal,
    tank_cals: dict[int, AffineTempCal],
) -> None:

    # Buffer
    for cn in sorted(db.h0cn.buffer.effective):

        device = db.h0cn.buffer.effective_to_device(cn)
        depth = db.h0cn.buffer.device_depth(device)

        cal = buffer_cal.calibration_for_depth(depth)

        add_temperature_channel(
            db,
            node_name=H0N.derived_generator,
            channel_name=cn,
            input_channel=device,
            calibration=cal,
        )

    # Tanks
    for tank_idx, tank in db.h0cn.tank.items():

        for cn in sorted(tank.effective):

            device = tank.effective_to_device(cn)
            depth = tank.device_depth(device)

            cal = tank_cals[tank_idx].calibration_for_depth(depth)

            add_temperature_channel(
                db,
                node_name=H0N.derived_generator,
                channel_name=cn,
                input_channel=device,
                calibration=cal,
            )