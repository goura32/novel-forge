"""Character name deduplication — tracks used names across all series."""

from __future__ import annotations

import json
from pathlib import Path

_NAMES_FILE = "used_names.json"


def load_used_names(workdir: Path) -> set[str]:
    """Load set of character names used across all series."""
    path = workdir / _NAMES_FILE
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("names", []))
    except Exception:
        return set()


def save_used_names(workdir: Path, names: set[str]) -> None:
    """Persist used names to disk."""
    path = workdir / _NAMES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"names": sorted(names)}, ensure_ascii=False, indent=2), encoding="utf-8")


def record_names(workdir: Path, new_names: set[str]) -> None:
    """Add new names to the used names file."""
    used = load_used_names(workdir)
    used.update(new_names)
    save_used_names(workdir, used)
