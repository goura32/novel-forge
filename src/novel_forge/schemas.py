from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from novel_forge.logging_config import get_logger

_log = get_logger("novel_forge.schemas")

_SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "schemas"

_SCHEMA_BY_NAME: dict[str, dict[str, Any]] = {}


def validate_schemas() -> list[str]:
    """Validate all schema files. Returns list of error messages (empty = all OK)."""
    errors: list[str] = []
    if not _SCHEMA_DIR.exists():
        return [f"Schema directory not found: {_SCHEMA_DIR}"]

    for path in sorted(_SCHEMA_DIR.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"{path.name}: {e}")

    return errors


def _load_schema(name: str) -> dict[str, Any]:
    if name not in _SCHEMA_BY_NAME:
        path = _SCHEMA_DIR / f"{name}.json"
        if not path.exists():
            available = sorted(p.stem for p in _SCHEMA_DIR.glob("*.json"))
            _log.error(
                "Schema not found: %s (requested: '%s', available: %s)", path, name, available
            )
            raise FileNotFoundError(f"Schema not found: {path}")
        with open(path, encoding="utf-8") as f:
            _SCHEMA_BY_NAME[name] = json.load(f)
    return _SCHEMA_BY_NAME[name]


def _validate_with_schema(schema: dict[str, Any], data: dict[str, Any]) -> list[str]:
    """Validate data against a loaded schema. Returns list of error messages."""
    errors = []
    for error in Draft202012Validator(schema).iter_errors(data):
        path = "/".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"[{path}] {error.message}")
    return errors


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
            _log.debug(
                "Coerced expected array '%s' (got object: %r) to []",
                key, type(data[key])
            )
            data[key] = []
    
    return data


def validate(name: str, data: dict[str, Any]) -> list[str]:
    """スキーマ検証。エラーリストを返す。"""
    try:
        schema = _load_schema(name)
    except FileNotFoundError:
        return []
    # Apply pre-validation coercion for common LLM output quirks
    coerce_array_fields(data, schema)
    return _validate_with_schema(schema, data)


def validate_or_raise(name: str, data: dict[str, Any]) -> None:
    errors = validate(name, data)
    if errors:
        raise ValidationError(f"Schema validation failed for '{name}:\n" + "\n".join(errors))


def get_schema(name: str) -> dict[str, Any]:
    try:
        return _load_schema(name)
    except FileNotFoundError:
        return {}


def list_schemas() -> list[str]:
    return [p.stem for p in _SCHEMA_DIR.glob("*.json")]
