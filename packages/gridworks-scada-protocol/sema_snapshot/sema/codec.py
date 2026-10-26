import json
import logging
from importlib import import_module
from collections import defaultdict
from pathlib import Path
from typing import Literal, TypeVar, overload


from sema_snapshot.sema.base import (
    DegradedSemaType,
    SemaType,
    pascal_to_snake,
    recursively_pascal,
    snake_to_pascal,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=SemaType)


class SemaCodec:
    def __init__(self) -> None:
        self.registry = get_current_types()
        self.old_versions = get_old_versions()

    # ------------------------------------------------------------------------
    # Decode
    # ------------------------------------------------------------------------

    @overload
    def from_dict(
        self,
        data: dict,
        mode: Literal["strict", "degraded"] = "strict",
        auto_upgrade: bool = True,
        *,
        expect: type[T],
    ) -> T: ...

    @overload
    def from_dict(
        self,
        data: dict,
        mode: Literal["strict", "degraded"] = "strict",
        auto_upgrade: bool = True,
        expect: None = None,
    ) -> SemaType | DegradedSemaType: ...

    def from_dict(
        self,
        data: dict,
        mode: Literal["strict", "degraded"] = "strict",
        auto_upgrade: bool = True,
        expect: type[T] | None = None,
    ) -> SemaType | DegradedSemaType:
        decoded = self._decode(data, mode, auto_upgrade)
        if expect is not None and not isinstance(decoded, expect):
            raise ValueError(
                f"decoded {type(decoded).__name__}, expected {expect.__name__}"
            )
        return decoded

    @overload
    def from_file(
        self,
        path: str | Path,
        mode: Literal["strict", "degraded"] = "strict",
        auto_upgrade: bool = True,
        *,
        expect: type[T],
    ) -> T: ...

    @overload
    def from_file(
        self,
        path: str | Path,
        mode: Literal["strict", "degraded"] = "strict",
        auto_upgrade: bool = True,
        expect: None = None,
    ) -> SemaType | DegradedSemaType: ...

    def from_file(
        self,
        path: str | Path,
        mode: Literal["strict", "degraded"] = "strict",
        auto_upgrade: bool = True,
        expect: type[T] | None = None,
    ) -> SemaType | DegradedSemaType:
        with open(path) as f:
            return self.from_dict(json.load(f), mode, auto_upgrade, expect=expect)

    def _decode(
        self,
        data: dict,
        mode: Literal["strict", "degraded"] = "strict",
        auto_upgrade: bool = True,
    ) -> SemaType | DegradedSemaType:
        if not isinstance(data, dict):
            raise ValueError("Input must be dict")

        if "TypeName" not in data:
            raise ValueError("Missing TypeName")

        if not recursively_pascal(data := dict(data)):
            raise ValueError("Input must be PascalCase")

        type_name = data["TypeName"]
        version = data.get("Version")

        if type_name not in self.registry:
            if mode == "degraded":
                return DegradedSemaType(
                    type_name=type_name,
                    version=version,
                    raw=data,
                    known_fields={},
                    unknown_fields=data,
                )
            raise ValueError(f"Unknown type {type_name}")

        current_cls = self.registry[type_name]
        current_version = current_cls.version_value()

        # Fast path
        if version == current_version:
            return current_cls.from_dict(data)

        # Old version
        if type_name in self.old_versions and version in self.old_versions[type_name]:
            old_cls = self.old_versions[type_name][version]
            old_instance = old_cls.from_dict(data)
            return (
                old_instance.to_latest(self.registry) if auto_upgrade else old_instance
            )

        # Unknown version
        if mode == "strict":
            raise ValueError(f"Unsupported version {version} for {type_name}")

        # --------------------------------------------------------------------
        # DEGRADED MODE
        # --------------------------------------------------------------------

        logger.warning(
            "Degraded decode for %s v%s (current v%s)",
            type_name,
            version,
            current_version,
        )

        valid_fields = set()
        for field_name, field_info in current_cls.model_fields.items():
            valid_fields.add(snake_to_pascal(field_name))
            valid_fields.add(field_name)
            if field_info.alias:
                valid_fields.add(field_info.alias)

        known = {}
        unknown = {}

        for key, value in data.items():
            if key in valid_fields or pascal_to_snake(key) in valid_fields:
                known[key] = value
            else:
                unknown[key] = value

        return DegradedSemaType(
            type_name=type_name,
            version=version,
            raw=data,
            known_fields=known,
            unknown_fields=unknown,
        )

    def from_bytes(
        self,
        data: bytes,
        mode: Literal["strict", "degraded"] = "strict",
    ) -> SemaType | DegradedSemaType:
        try:
            d = json.loads(data.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"Invalid JSON: {e}") from e

        return self.from_dict(d, mode=mode)

    def to_bytes(self, msg: SemaType) -> bytes:
        return msg.to_bytes()


# ============================================================================
# AUTO-DISCOVERY
# ============================================================================


def get_current_types() -> dict[str, type[SemaType]]:
    from sema_snapshot.sema import types

    return {
        getattr(types, name).type_name_value(): getattr(types, name)
        for name in types.__all__
    }


def get_old_versions() -> dict[str, dict[str | None, type[SemaType]]]:
    registry: dict[str, dict[str | None, type[SemaType]]] = defaultdict(dict)
    old_versions_dir = Path(__file__).resolve().parent / "types" / "old_versions"

    for path in sorted(old_versions_dir.glob("*.py")):
        if path.stem == "__init__":
            continue
        module = import_module(f"sema_snapshot.sema.types.old_versions.{path.stem}")
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, SemaType)
                and obj is not SemaType
            ):
                version = obj.version_value()
                if version is not None:
                    registry[obj.type_name_value()][version] = obj

    return registry


default_codec = SemaCodec()
