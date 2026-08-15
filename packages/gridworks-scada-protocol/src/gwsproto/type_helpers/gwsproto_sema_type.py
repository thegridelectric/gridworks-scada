"""The base every gwsproto sema word inherits: identity accessors, nothing else.

Fieldless and config-less by construction, and both halves are load-bearing.

gwproto's payload discovery (``gwproto/decoders.py`` ``get_candidate_payload_classes``)
admits a class into a discriminated union only if it declares a field literally
named ``TypeName`` whose annotation is a ``Literal``. A base declaring no
``TypeName`` field is therefore invisible to discovery, while every subclass is
found exactly as before. Declaring ``model_config`` would be worse than
unnecessary: pydantic merges a base's config into every subclass, even one that
declares its own, so a ``frozen``/``extra="forbid"`` base would silently
reconfigure every word.

Method names match sema's own runtime (``SemaType``) and gwbase's vendored copy
of it, so call sites survive the proactor port unchanged.
"""

from typing import Optional

from pydantic import BaseModel


class GwsprotoSemaType(BaseModel):
    """A gwsproto sema word. Adds identity accessors; adds no fields and no config."""

    @classmethod
    def type_name_value(cls) -> str:
        """The word's TypeName, e.g. ``gw.nolan.layout``."""
        field = cls.model_fields.get("TypeName")
        if field is None:
            raise ValueError(f"{cls.__name__} has no TypeName field")
        return str(field.default)

    @classmethod
    def version_value(cls) -> Optional[str]:
        """The word's Version, e.g. ``000``; None if the word declares none."""
        field = cls.model_fields.get("Version")
        return None if field is None else str(field.default)
