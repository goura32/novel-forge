from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

_SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "schemas"

_SCHEMA_BY_NAME: dict[str, dict[str, Any]] = {}


def _load_schema(name: str) -> dict[str, Any]:
    if name not in _SCHEMA_BY_NAME:
        path = _SCHEMA_DIR / f"{name}.json"
        if not path.exists():
            import sys as _sys
            available = sorted(p.stem for p in _SCHEMA_DIR.glob("*.json"))
            _sys.stderr.write(f"  [SCHEMA ERROR] Schema not found: {path}\n")
            _sys.stderr.write(f"  [SCHEMA ERROR] Requested: '{name}'\n")
            _sys.stderr.write(f"  [SCHEMA ERROR] Available schemas: {available}\n")
            raise FileNotFoundError(f"Schema not found: {path}")
        with open(path, encoding="utf-8") as f:
            _SCHEMA_BY_NAME[name] = json.load(f)
    return _SCHEMA_BY_NAME[name]


def validate(name: str, data: dict[str, Any]) -> list[str]:
    schema = _load_schema(name)
    validator = Draft202012Validator(schema)
    errors = []
    for error in validator.iter_errors(data):
        path = "/".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"[{path}] {error.message}")
    return errors


def validate_or_raise(name: str, data: dict[str, Any]) -> None:
    errors = validate(name, data)
    if errors:
        raise ValidationError(
            f"Schema validation failed for '{name}':\n" + "\n".join(errors)
        )


def get_schema(name: str) -> dict[str, Any]:
    return _load_schema(name)


def list_schemas() -> list[str]:
    return [p.stem for p in _SCHEMA_DIR.glob("*.json")]
