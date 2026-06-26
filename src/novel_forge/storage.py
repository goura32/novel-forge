from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from novel_forge.models import Bible, Blackboard, ProjectState


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
        except json.JSONDecodeError, Exception:
            if self._backup_path.exists():
                try:
                    data = json.loads(self._backup_path.read_text(encoding="utf-8"))
                    return ProjectState(**data)
                except json.JSONDecodeError, Exception:
                    pass
            return ProjectState(workdir=str(self._workdir))

    def save(self, state: ProjectState) -> None:
        if self._state_path.exists():
            self._backup_path.write_text(
                self._state_path.read_text(encoding="utf-8"), encoding="utf-8"
            )
        _atomic_write(self._state_path, _model_to_json(state))


class BlackboardStorage:
    def __init__(self, workdir: Path):
        self._path = workdir / "blackboard.json"

    def load(self) -> Blackboard:
        if not self._path.exists():
            return Blackboard()
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return Blackboard(**data)

    def save(self, blackboard: Blackboard) -> None:
        _atomic_write(self._path, _model_to_json(blackboard))


class BibleStorage:
    def __init__(self, workdir: Path):
        self._path = workdir / "bible.json"

    def load(self) -> Bible:
        if not self._path.exists():
            return Bible()
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return Bible(**data)

    def save(self, bible: Bible) -> None:
        _atomic_write(self._path, _model_to_json(bible))
