"""Repository helpers for project artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ProjectRepository:
    def __init__(self, root: Path):
        self.root = root

    def save_json(self, relative_path: str | Path, data: dict[str, Any]) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load_json(self, relative_path: str | Path) -> dict[str, Any]:
        return json.loads((self.root / relative_path).read_text(encoding="utf-8"))

    def write_text(self, relative_path: str | Path, content: str) -> Path:
        path = self.root / relative_path
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
