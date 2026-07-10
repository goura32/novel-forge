"""Canon schema registry (§9).

Loads the committed ``model_json_schema()``-generated artifacts and builds a
``referencing.Registry`` so that external ``$ref`` values resolve
deterministically.

§9 mandates:
  * every schema carries a fixed ``$id``
  * ``referencing.Registry`` holds all schemas
  * validation uses ``Draft202012Validator(schema, registry=registry)``
  * a sibling ``$ref`` must NOT be resolved by ``Draft202012Validator(schema)`` alone
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

_SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

# Schema names committed under src/novel_forge/canon/schemas/.
_SCHEMA_NAMES = (
    "canon_patch",
    "design_intent",
    "context_scope",
    "writer_context",
    "entity_ref",
    "source_ref",
    "canon",
    "scene_design",
)


def _load_raw(name: str) -> dict[str, Any]:
    path = _SCHEMA_DIR / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Canon schema not found: {path}")
    return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def build_registry() -> Registry:
    """Build a ``referencing.Registry`` from all committed canon schemas."""
    resources: list[Resource] = []
    for name in _SCHEMA_NAMES:
        raw = _load_raw(name)
        resources.append(Resource.from_contents(raw))
    return Registry().with_resources(
        [(res.contents["$id"], res) for res in resources]
    )


def get_schema(name: str) -> dict[str, Any]:
    """Return a raw schema document (unmodified from disk)."""
    return _load_raw(name)


def get_validator(name: str) -> Draft202012Validator:
    """Return a ``Draft202012Validator`` bound to the shared registry (§9)."""
    schema = get_schema(name)
    return Draft202012Validator(schema, registry=build_registry())


def validate(name: str, data: dict[str, Any]) -> list[str]:
    """Validate ``data`` against schema ``name``.

    Returns a list of human-readable error strings (empty = valid).
    """
    validator = get_validator(name)
    errors: list[str] = []
    for error in validator.iter_errors(data):
        path = "/".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"[{path}] {error.message}")
    return errors


def validate_or_raise(name: str, data: dict[str, Any]) -> None:
    errors = validate(name, data)
    if errors:
        from jsonschema import ValidationError

        raise ValidationError(
            f"Canon schema '{name}' validation failed:\n" + "\n".join(errors)
        )
