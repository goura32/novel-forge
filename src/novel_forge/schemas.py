from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from novel_forge.logging_config import get_logger

_log = get_logger("novel_forge.schemas")

_DEV_SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "schemas"
_PACKAGED_SCHEMA_DIR = resources.files("novel_forge") / "resources" / "schemas"
_SCHEMA_DIR = _DEV_SCHEMA_DIR if _DEV_SCHEMA_DIR.exists() else _PACKAGED_SCHEMA_DIR

_SCHEMA_BY_NAME: dict[str, dict[str, Any]] = {}


def _schema_files():
    return sorted(
        (p for p in _SCHEMA_DIR.iterdir() if p.name.endswith(".json")),
        key=lambda p: p.name,
    )


def validate_schemas() -> list[str]:
    """Validate all schema files. Returns list of error messages (empty = all OK)."""
    errors: list[str] = []
    if not _SCHEMA_DIR.is_dir():
        return [f"Schema directory not found: {_SCHEMA_DIR}"]

    for path in _schema_files():
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{path.name}: {e}")

    return errors


def _load_schema(name: str) -> dict[str, Any]:
    if name not in _SCHEMA_BY_NAME:
        path = _SCHEMA_DIR / f"{name}.json"
        if not path.is_file():
            available = sorted(p.name.removesuffix(".json") for p in _schema_files())
            _log.error(
                "Schema not found: %s (requested: '%s', available: %s)", path, name, available
            )
            raise FileNotFoundError(f"Schema not found: {path}")
        _SCHEMA_BY_NAME[name] = json.loads(path.read_text(encoding="utf-8"))
    return _SCHEMA_BY_NAME[name]


def _validate_with_schema(schema: dict[str, Any], data: dict[str, Any]) -> list[str]:
    """Validate data against a loaded schema. Returns list of error messages."""
    errors = []
    for error in Draft202012Validator(schema).iter_errors(data):
        path = "/".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"[{path}] {error.message}")
    return errors


def _validate_review_readiness(data: dict[str, Any]) -> list[str]:
    has_blocking = any(
        isinstance(issue, dict) and issue.get("publication_blocking") is True
        for issue in data.get("issues", [])
    )
    if data.get("ready_for_publication") is True and has_blocking:
        return ["ready_for_publication=true cannot have publication_blocking=true issues"]
    if data.get("ready_for_publication") is False and not has_blocking:
        return ["ready_for_publication=false requires at least one publication_blocking=true issue"]
    return []


def coerce_array_fields(data: dict, schema: dict) -> dict:
    """Pre-validation coercion: convert expected array fields that are objects to [].
    
    This fixes common LLM quirks where it returns {} or {"a": "b"} instead of []
    for array-typed fields (e.g., issues as object instead of list).
    """
    if not schema or not isinstance(data, dict):
        return data
    
    properties = schema.get("properties", {})
    for key, prop_schema in properties.items():
        if key in data and isinstance(data[key], dict) and prop_schema.get("type") == "array":
            # If an array field is actually returned as object from LLM, replace with []
            _log.warning(
                "Coerced schema array field '%s' from object to []",
                key,
            )
            data[key] = []
    
    return data


def _coerce_enum_prefixes_in_container(data: Any, schema: dict[str, Any]) -> None:
    """Coerce enum strings like ``導入：説明`` to ``導入`` when safe."""
    if isinstance(data, dict):
        for key, prop_schema in schema.get("properties", {}).items():
            if key not in data:
                continue
            value = data[key]
            enum_values = prop_schema.get("enum") if isinstance(prop_schema, dict) else None
            if isinstance(value, str) and isinstance(enum_values, list):
                separators = ("：", ":", "、", "，", " ", "　", "-", "—", "─", "(", "（")
                for enum_value in sorted((str(v) for v in enum_values), key=len, reverse=True):
                    if value.startswith(tuple(enum_value + sep for sep in separators)):
                        _log.warning("Coerced enum field '%s' from %r to %r", key, value, enum_value)
                        data[key] = enum_value
                        break
            _coerce_enum_prefixes_in_container(data[key], prop_schema)
    elif isinstance(data, list):
        item_schema = schema.get("items", {})
        for item in data:
            _coerce_enum_prefixes_in_container(item, item_schema)
def validate(name: str, data: dict[str, Any]) -> list[str]:
    """スキーマ検証。エラーリストを返す。"""
    try:
        schema = _load_schema(name)
    except FileNotFoundError:
        return [f"Schema not found: {name}"]
    return validate_data(name, schema, data)


def validate_data(name: str, schema: dict[str, Any], data: dict[str, Any]) -> list[str]:
    """Validate data against an already loaded schema."""
    # Apply pre-validation coercion for common LLM output quirks.
    # This mutates data intentionally, matching validate(name, data) behavior.
    coerce_array_fields(data, schema)
    _coerce_enum_prefixes_in_container(data, schema)
    errors = _validate_with_schema(schema, data)
    if name == "review" and not errors:
        errors.extend(_validate_review_readiness(data))
    return errors


def validate_or_raise(name: str, data: dict[str, Any]) -> None:
    errors = validate(name, data)
    if errors:
        raise ValidationError(f"Schema validation failed for '{name}:\n" + "\n".join(errors))


def validate_data_or_raise(name: str, schema: dict[str, Any], data: dict[str, Any]) -> None:
    errors = validate_data(name, schema, data)
    if errors:
        raise ValidationError(f"Schema validation failed for '{name}:\n" + "\n".join(errors))


def get_schema(name: str) -> dict[str, Any]:
    return _load_schema(name)


def list_schemas() -> list[str]:
    return [p.name.removesuffix(".json") for p in _schema_files()]
