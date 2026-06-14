from pydantic import BaseModel, ConfigDict, PositiveInt


class ComponentAttributeClassGt(BaseModel):
    """
    Device-type record base. A component joins its specialized record (when one exists)
    by the shared ``DeviceType`` value — a ``gw1.device.type`` member, replacing the legacy
    ``component.attribute.class.gt`` UUID + ``CACS_BY_MAKE_MODEL`` bijection and its
    make/model-as-identity. A record-less device category needs only the base record (its
    ``DeviceType`` + ``DisplayName``); scada app code dispatches on ``DeviceType``.
    """

    DeviceType: str
    DisplayName: str | None = None
    MinPollPeriodMs: PositiveInt | None = None
    TypeName: str = "component.attribute.class.gt"
    Version: str = "002"

    model_config = ConfigDict(use_enum_values=True, extra="allow")
