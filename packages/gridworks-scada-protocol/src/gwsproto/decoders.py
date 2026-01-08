import re
from typing import Any, Optional
from pydantic import ValidationError

from gwproto.decoders import UnionDecoder, UnionWrapper

from gwsproto.named_types import ComponentAttributeClassGt, ComponentGt

class CacDecoder(UnionDecoder):
    TYPE_NAME_REGEX = re.compile(r".*\.cac\.gt")
    loader: type[UnionWrapper[Any]]

    def __init__(
        self,
        model_name: str,
        type_name_regex: Optional[re.Pattern[str]] = TYPE_NAME_REGEX,
        **kwargs: Any,
    ) -> None:
        super().__init__(model_name, type_name_regex=type_name_regex, **kwargs)

    def decode(
        self, cac_dict: dict[str, Any], *, allow_missing: bool = True
    ) -> ComponentAttributeClassGt:
        decoded: ComponentAttributeClassGt
        try:
            decoded = self.loader.model_validate({"Wrapped": cac_dict}).Wrapped
            if not isinstance(decoded, ComponentAttributeClassGt):
                raise TypeError(
                    f"ERROR. CacDecoder decoded type {type(decoded)}, "
                    "not ComponentAttributeClassGt"
                )
        except ValidationError as e:
            if allow_missing and any(
                error.get("type") == "union_tag_invalid" for error in e.errors()
            ):
                decoded = ComponentAttributeClassGt(**cac_dict)
            else:
                raise
        return decoded


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
    ) -> ComponentGt:
        decoded: ComponentGt
        try:
            # Pydantic requires that our union of types (components here) be in
            # a named field, which by convention we call "Wrapped".
            decoded = self.loader.model_validate({"Wrapped": component_dict}).Wrapped
            if not isinstance(decoded, ComponentGt):
                raise TypeError(
                    f"ERROR. ComponentDecoder decoded type {type(decoded)}, "
                    "not ComponentGt"
                )
        except ValidationError as e:
            if allow_missing and any(
                error.get("type") == "union_tag_invalid" for error in e.errors()
            ):
                decoded = ComponentGt(**component_dict)
            else:
                raise
        return decoded
