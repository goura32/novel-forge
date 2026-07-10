"""§9 schema registry contract tests.

Verifies that committed generated JSON Schemas are loaded into a
``referencing.Registry`` and that ``$ref`` resolution requires the registry
(a sibling ``$ref`` must NOT resolve with ``Draft202012Validator(schema)`` alone).
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from novel_forge.canon.models import CanonPatch
from novel_forge.canon.registry import (
    build_registry,
    get_schema,
    get_validator,
    validate,
)

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "src" / "novel_forge" / "canon" / "schemas"


def test_registry_builds_and_resolves_canon_patch() -> None:
    reg = build_registry()
    assert reg is not None
    # canon_patch is retrievable by its fixed $id.
    res = reg.get_or_retrieve("https://novel-forge.local/schemas/canon/canon_patch.json")
    assert res.value.contents["$id"] == "https://novel-forge.local/schemas/canon/canon_patch.json"


def test_valid_canon_patch_validates_via_registry() -> None:
    data = CanonPatch().model_dump(mode="json")
    errors = validate("canon_patch", data)
    assert errors == [], errors


def test_scene_design_ref_resolves_through_registry() -> None:
    sd_validator = get_validator("scene_design")
    sd_data = {
        "canon_patch": CanonPatch().model_dump(mode="json"),
        "context_scope": {"pov_character": {"kind": "character", "id": "char_001"}},
    }
    errs = list(sd_validator.iter_errors(sd_data))
    assert errs == [], [e.message for e in errs]


def test_unresolved_ref_fails_without_registry() -> None:
    # §9: a sibling $ref must NOT be resolved by Draft202012Validator(schema) alone.
    # Without the registry, jsonschema cannot resolve the canon_patch.json $ref
    # and raises an Unresolvable error instead of silently validating.
    import pytest

    raw = json.loads((_SCHEMA_DIR / "scene_design.json").read_text(encoding="utf-8"))
    lonely = Draft202012Validator(raw)
    sd_data = {"canon_patch": CanonPatch().model_dump(mode="json")}
    with pytest.raises(Exception) as exc_info:
        list(lonely.iter_errors(sd_data))
    assert "Unresolvable" in str(exc_info.value)


def test_all_committed_schemas_have_fixed_id() -> None:
    for name in ("canon_patch", "design_intent", "context_scope", "writer_context",
                 "entity_ref", "source_ref", "canon", "scene_design"):
        raw = get_schema(name)
        assert raw.get("$id") == f"https://novel-forge.local/schemas/canon/{name}.json", name
        assert raw.get("$schema") == "https://json-schema.org/draft/2020-12/schema", name
