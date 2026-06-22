"""Validate all JSON schema files are parseable.

Called during engine init to catch schema errors early.
"""

import json
import sys
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "schemas"


def validate_schemas() -> list[str]:
    """Validate all schema files. Returns list of error messages (empty = all OK)."""
    errors: list[str] = []
    if not SCHEMA_DIR.exists():
        return [f"Schema directory not found: {SCHEMA_DIR}"]

    for path in sorted(SCHEMA_DIR.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"{path.name}: {e}")

    return errors
