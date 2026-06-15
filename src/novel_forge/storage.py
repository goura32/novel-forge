from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from novel_forge.models import ProjectState, Blackboard, Bible


class StateStorage:
    def __init__(self, workdir: Path):
        self._workdir = workdir
        self._state_path = workdir / ".novel-forge" / "state.json"
        self._backup_path = workdir / ".novel-forge" / "state.json.bak"

    def load(self) -> ProjectState:
        if not self._state_path.exists():
            return ProjectState(workdir=str(self._workdir))
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            return ProjectState(**data)
        except (json.JSONDecodeError, Exception):
            if self._backup_path.exists():
                data = json.loads(self._backup_path.read_text(encoding="utf-8"))
                return ProjectState(**data)
            return ProjectState(workdir=str(self._workdir))

    def save(self, state: ProjectState) -> None:
        self._workdir.mkdir(parents=True, exist_ok=True)
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        if self._state_path.exists():
            self._backup_path.write_text(
                self._state_path.read_text(encoding="utf-8"), encoding="utf-8"
            )
        data = json.loads(state.model_dump_json())
        content = json.dumps(data, ensure_ascii=False, indent=2)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._state_path.parent), suffix=".tmp"
        )
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            os.rename(tmp_path, self._state_path)
        except Exception:
            os.close(fd)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise


class BlackboardStorage:
    def __init__(self, workdir: Path):
        self._path = workdir / ".novel-forge" / "blackboard.json"

    def load(self) -> Blackboard:
        if not self._path.exists():
            return Blackboard()
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return Blackboard(**data)

    def save(self, blackboard: Blackboard) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(blackboard.model_dump_json())
        content = json.dumps(data, ensure_ascii=False, indent=2)
        fd, tmp_path = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            os.rename(tmp_path, self._path)
        except Exception:
            os.close(fd)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise


class BibleStorage:
    def __init__(self, workdir: Path):
        self._path = workdir / ".novel-forge" / "bible.json"

    def load(self) -> Bible:
        if not self._path.exists():
            return Bible()
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return Bible(**data)

    def save(self, bible: Bible) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(bible.model_dump_json())
        content = json.dumps(data, ensure_ascii=False, indent=2)
        fd, tmp_path = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            os.rename(tmp_path, self._path)
        except Exception:
            os.close(fd)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
