"""sema_to_dc maps one TypeName/Version pair onto each data class.

The scada speaks the one version of each word in its snapshot. For every
artifact the module decodes, and every word it decodes into a typed class
along the way, the decode SHALL accept the authored version and SHALL
refuse every other, and what it accepts it SHALL return unchanged. A lift,
an upgrade or a default written in before validation is a second version
of one TypeName mapped onto the same class, and fails here. A word inside
a free-object field is not mapped to a class by the decode and is not
tested here."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from gwsproto.type_helpers.component_base import GwsprotoSemaType
from sema_to_dc import SEMA_LAYOUT_BY_TYPENAME, decode_operational_params

CONFIG = Path(__file__).parent.parent / "config"
ARTIFACTS = sorted(CONFIG.glob("*operational.params.json")) + sorted(CONFIG.glob("*.layout.json"))
OTHER_VERSIONS = ("000", "001", "002", "003", "004", "005", "999")


def decode(d: dict[str, Any]) -> GwsprotoSemaType:
    """The module's decode for an authored artifact, by its TypeName."""
    if d["TypeName"] in SEMA_LAYOUT_BY_TYPENAME:
        return SEMA_LAYOUT_BY_TYPENAME[d["TypeName"]].model_validate(d)
    return decode_operational_params(d)


def mapped_words(word: Any, path: tuple[Any, ...] = ()) -> list[tuple[tuple[Any, ...], str, str]]:
    """Every (path, TypeName, Version) the decode mapped onto a typed class:
    the root and each nested GwsprotoSemaType, by the wire (alias) path."""
    found = []
    if isinstance(word, GwsprotoSemaType):
        found.append((path, word.TypeName, word.Version))
    if isinstance(word, BaseModel):
        for name, field in type(word).model_fields.items():
            found.extend(mapped_words(getattr(word, name), (*path, field.alias or name)))
    elif isinstance(word, list):
        for i, item in enumerate(word):
            found.extend(mapped_words(item, (*path, i)))
    return found


def with_version(d: dict[str, Any], path: tuple[Any, ...], version: str) -> dict[str, Any]:
    """A deep copy of d with the word at path stamped version."""
    copy = json.loads(json.dumps(d))
    node: Any = copy
    for step in path:
        node = node[step]
    node["Version"] = version
    return copy


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.name)
def test_the_authored_artifact_decodes_and_round_trips(path: Path) -> None:
    d = json.loads(path.read_text())
    assert decode(d).model_dump(by_alias=True, exclude_none=True) == d


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.name)
def test_each_mapped_word_is_accepted_at_exactly_one_version(path: Path) -> None:
    d = json.loads(path.read_text())
    first_of_each: dict[tuple[str, str], tuple[Any, ...]] = {}
    for word_path, type_name, version in mapped_words(decode(d)):
        first_of_each.setdefault((type_name, version), word_path)
    assert first_of_each, "the decode mapped no word"
    accepted_elsewhere = []
    for (type_name, version), word_path in first_of_each.items():
        for other in OTHER_VERSIONS:
            if other == version:
                continue
            try:
                decode(with_version(d, word_path, other))
            except (ValidationError, ValueError):
                continue
            accepted_elsewhere.append(f"{type_name} {other} (authored {version}) at {list(word_path)}")
    assert not accepted_elsewhere, "\n".join(accepted_elsewhere)
