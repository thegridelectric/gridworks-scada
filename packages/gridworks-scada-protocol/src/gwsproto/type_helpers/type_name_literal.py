from typing import Type, get_args

from pydantic import BaseModel


def type_name_literal(model: Type[BaseModel]) -> str:
    "returns the TypeName of a Type"
    field = model.model_fields.get("TypeName")
    if not field:
        raise ValueError(f"{model.__name__} has no TypeName field")
    return get_args(field.annotation)[0]

