import re
from typing import Any, Optional
from pydantic import ValidationError  # noqa: F401  (kept for ComponentDecoder below)

from gwproto.decoders import UnionDecoder, UnionWrapper

from gwsproto.type_helpers.component_base import ComponentBase

# The decoded device-type record union (the per-family *.device.type.gt types).
DeviceTypeGt = Any


class DeviceTypeDecoder(UnionDecoder):
    """Decodes the per-family specialized device-type records (the successors to the
    legacy *.cac.gt machinery): ads111x.based.device.type.gt,
    electric.meter.device.type.gt, gw1.scada.device.type.gt."""

    TYPE_NAME_REGEX = re.compile(r".*\.device\.type\.gt")
    loader: type[UnionWrapper[Any]]

    def __init__(
        self,
        model_name: str,
        type_name_regex: Optional[re.Pattern[str]] = TYPE_NAME_REGEX,
        **kwargs: Any,
    ) -> None:
        super().__init__(model_name, type_name_regex=type_name_regex, **kwargs)

    def decode(self, dt_dict: dict[str, Any], *, allow_missing: bool = True) -> Any:
        return self.loader.model_validate({"Wrapped": dt_dict}).Wrapped


class ComponentDecoder(UnionDecoder):
    TYPE_NAME_REGEX = re.compile(r".*\.component\.gt")

    def __init__(
        self,
        model_name: str,
        type_name_regex: Optional[re.Pattern[str]] = TYPE_NAME_REGEX,
        **kwargs: Any,
    ) -> None:
        super().__init__(model_name, type_name_regex=type_name_regex, **kwargs)

    def decode(
        self, component_dict: dict[str, Any], *, allow_missing: bool = True
    ) -> ComponentBase:
        decoded: ComponentBase
        try:
            # Pydantic requires that our union of types (components here) be in
            # a named field, which by convention we call "Wrapped".
            decoded = self.loader.model_validate({"Wrapped": component_dict}).Wrapped
            if not isinstance(decoded, ComponentBase):
                raise TypeError(
                    f"ERROR. ComponentDecoder decoded type {type(decoded)}, "
                    "not a ComponentBase"
                )
        except ValidationError as e:
            if allow_missing and any(
                error.get("type") == "union_tag_invalid" for error in e.errors()
            ):
                decoded = ComponentBase(**component_dict)
            else:
                raise
        return decoded
