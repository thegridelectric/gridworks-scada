from pydantic import BaseModel, ConfigDict, PositiveInt

from gwsproto.enums import MakeModel as MakeModelEnum


class ComponentAttributeClassGt(BaseModel):
    """
    Device-type record base. A component joins its specialized record (when one exists)
    by the shared ``DeviceType`` value — a ``gw1.device.type`` enum member, replacing the
    legacy ``component.attribute.class.gt`` UUID + ``CACS_BY_MAKE_MODEL`` bijection.

    ``MakeModel`` is retained as informational/dispatch detail (some actors still read it),
    but it is no longer the identity and carries no axiom. A record-less device category
    needs only the base record (its ``DeviceType`` + ``DisplayName``).
    """

    DeviceType: str
    DisplayName: str | None = None
    MakeModel: MakeModelEnum | None = None
    MinPollPeriodMs: PositiveInt | None = None
    TypeName: str = "component.attribute.class.gt"
    Version: str = "002"

    model_config = ConfigDict(use_enum_values=True, extra="allow")
