from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from novel_forge.logging_config import get_logger
from novel_forge.models import ProjectState

_log = get_logger("novel_forge.storage")


def _atomic_write(path: Path, content: str) -> None:
    """ファイルをアトミックに書き込む。書き込み中のクラッシュによる破損を防ぐ。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        fd = -1
        os.rename(tmp_path, path)
    except Exception:
        if fd >= 0:
            os.close(fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _model_to_json(model: Any) -> str:
    """PydanticモデルをJSON文字列に変換する。"""
    return json.dumps(model.model_dump(), ensure_ascii=False, indent=2)


class StateStorage:
    def __init__(self, workdir: Path):
        self._workdir = workdir
        self._state_path = workdir / "state.json"
        self._backup_path = workdir / "state.json.bak"

    def load(self) -> ProjectState:
        if not self._state_path.exists():
            return ProjectState(workdir=str(self._workdir))
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            return ProjectState(**data)
        except Exception as exc:
            _log.warning("Failed to load state file; attempting backup: %s", self._state_path, exc_info=exc)
            if self._backup_path.exists():
                try:
                    data = json.loads(self._backup_path.read_text(encoding="utf-8"))
                    return ProjectState(**data)
                except Exception as backup_exc:
                    _log.warning(
                        "Failed to load state backup; using default state: %s",
                        self._backup_path,
                        exc_info=backup_exc,
                    )
            else:
                _log.warning("State backup not found; using default state: %s", self._backup_path)
            return ProjectState(workdir=str(self._workdir))

    def save(self, state: ProjectState) -> None:
        # Snapshot the current state into the backup path atomically before
        # replacing the live file, so a crash mid-write never leaves a
        # half-written or stale backup.
        if self._state_path.exists():
            try:
                current = self._state_path.read_text(encoding="utf-8")
                _atomic_write(self._backup_path, current)
            except OSError as exc:
                _log.warning("Failed to snapshot state backup: %s", self._backup_path, exc_info=exc)
        _atomic_write(self._state_path, _model_to_json(state))
