"""Repository helpers for project artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


def safe_join(root: Path, relative_path: str | Path) -> Path:
    """Join a repository-relative path and reject absolute/parent escapes."""
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValueError(f"Path escapes repository root: {relative_path}")
    root_resolved = root.resolve()
    path = (root / candidate).resolve()
    if path != root_resolved and root_resolved not in path.parents:
        raise ValueError(f"Path escapes repository root: {relative_path}")
    return path


class ProjectRepository:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, relative_path: str | Path) -> Path:
        return safe_join(self.root, relative_path)

    def save_json(self, relative_path: str | Path, data: dict[str, Any]) -> Path:
        path = self._path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load_json(self, relative_path: str | Path) -> dict[str, Any]:
        data = json.loads(self._path(relative_path).read_text(encoding="utf-8"))
        return cast(dict[str, Any], data)

    def write_text(self, relative_path: str | Path, content: str) -> Path:
        path = self._path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


class RawLogRepository:
    def __init__(self, root: Path):
        self.root = root

    def phase_dir(self, phase: str) -> Path:
        path = self.root / "_raw_logs" / phase
        path.mkdir(parents=True, exist_ok=True)
        return path
