from enum import StrEnum
from typing import Any, Self


class GwStrEnum(StrEnum):
    """
    Mimics fastapi-utils use of StrEnum, which diverges from the
    python-native StrEnum for python 3.11+.  Also, fills in with default
    value if a string does not exist in the enum.

    Specifically (re difference with python StrEnum) if

    class Foo(Enum):
        Bar = auto()

    then

    Foo.Bar.value is 'Bar' (instead of 'bar')

    """

    @staticmethod
    def _generate_next_value_(
        name: str,
        start: int,  # noqa: ARG004
        count: int,  # noqa: ARG004
        last_values: list[Any],  # noqa: ARG004
    ) -> str:
        return name

    @classmethod
    def values(cls) -> list[str]:
        return [str(elt) for elt in cls]

    @classmethod
    def default(cls) -> Self | None:
        return None

    @classmethod
    def _missing_(cls, value: object) -> Self:
        default = cls.default()
        if default is None:
            raise ValueError(f"'{value}' is not valid {cls.__name__}")
        return default


class SemaEnum(GwStrEnum):
    """
    Base for enums published in Sema.
    Requires enum_name(). Version is optional (return None for stable enums).
    """

    @classmethod
    def enum_name(cls) -> str:
        """Sema identifier (e.g., 'gw1.relay.state')"""
        raise NotImplementedError(f"{cls.__name__} must implement enum_name() for Sema")

    @classmethod
    def enum_version(cls) -> str:
        """Sema identifier (e.g., '000')"""
        raise NotImplementedError(f"{cls.__name__} must implement enum_name() for Sema")


class SymbolizedEnum(SemaEnum):
    @classmethod
    def symbol_to_value(cls, symbol: str) -> str:
        raise NotImplementedError

    @classmethod
    def value_to_symbol(cls, value: str) -> str:
        raise NotImplementedError

    @classmethod
    def symbols(cls) -> list[str]:
        raise NotImplementedError
