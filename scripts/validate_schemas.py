#!/usr/bin/env python3
"""Validate all JSON schema files are parseable.

Usage:
    python scripts/validate_schemas.py

Exit code 0 if all schemas are valid, 1 if any fail.
"""

import json
import sys
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"


def main() -> int:
    if not SCHEMA_DIR.exists():
        print(f"Schema directory not found: {SCHEMA_DIR}")
        return 1

    schema_files = sorted(SCHEMA_DIR.glob("*.json"))
    if not schema_files:
        print("No schema files found.")
        return 1

    errors = []
    for path in schema_files:
        try:
            with open(path, encoding="utf-8") as f:
                json.load(f)
            print(f"  OK  {path.name}")
        except json.JSONDecodeError as e:
            print(f"  FAIL {path.name}: {e}")
            errors.append((path, str(e)))

    print()
    if errors:
        print(f"FAILED: {len(errors)} schema file(s) have errors")
        for path, err in errors:
            print(f"  {path.name}: {err}")
        return 1
    else:
        print(f"OK: All {len(schema_files)} schema files are valid")
        return 0


if __name__ == "__main__":
    sys.exit(main())
