"""Unit tests for repository helpers."""

from __future__ import annotations

from novel_forge.repository import ProjectRepository, RawLogRepository


def test_project_repository_saves_and_loads_json(tmp_path) -> None:
    repo = ProjectRepository(tmp_path)

    path = repo.save_json("vol01/data.json", {"title": "第一巻"})

    assert path.exists()
    assert repo.load_json("vol01/data.json") == {"title": "第一巻"}


def test_raw_log_repository_creates_phase_dir(tmp_path) -> None:
    repo = RawLogRepository(tmp_path)

    path = repo.phase_dir("design")

    assert path == tmp_path / "_raw_logs" / "design"
    assert path.exists()
