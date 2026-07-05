"""Security-focused tests for path resolution and repository writes."""

from __future__ import annotations

import pytest

from novel_forge.engine.infra import _find_existing_series
from novel_forge.repository import ProjectRepository


def test_find_existing_series_rejects_parent_directory_escape(tmp_path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "series_plan.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsafe series slug"):
        _find_existing_series(base, "../outside")


def test_project_repository_rejects_parent_directory_escape(tmp_path) -> None:
    repo = ProjectRepository(tmp_path / "root")

    with pytest.raises(ValueError, match="Path escapes repository root"):
        repo.save_json("../escape.json", {"bad": True})
