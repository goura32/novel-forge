"""Tests for storage.py — atomic save with backup."""

import logging

from novel_forge.models import Bible, Blackboard, CharacterProfile, ProjectState
from novel_forge.storage import BibleStorage, BlackboardStorage, StateStorage


class TestStateStorageAtomicSave:
    def test_save_creates_file(self, tmp_path):
        storage = StateStorage(tmp_path)
        state = ProjectState(series_title="Test", workdir=str(tmp_path))
        storage.save(state)
        assert (tmp_path / "state.json").exists()

    def test_save_creates_backup(self, tmp_path):
        storage = StateStorage(tmp_path)
        state = ProjectState(series_title="Test", workdir=str(tmp_path))
        storage.save(state)
        storage.save(state)  # Second save creates backup
        assert (tmp_path / "state.json.bak").exists()

    def test_corrupt_state_loads_backup(self, tmp_path, caplog):
        storage = StateStorage(tmp_path)
        state = ProjectState(series_title="Backup", workdir=str(tmp_path))
        storage.save(state)
        storage.save(state)  # Create backup
        # Corrupt main file
        (tmp_path / "state.json").write_text("not json", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="novel_forge.storage"):
            loaded = storage.load()
        assert loaded.series_title == "Backup"
        assert "Failed to load state file; attempting backup" in caplog.text

    def test_corrupt_both_returns_default_with_warning(self, tmp_path, caplog):
        storage = StateStorage(tmp_path)
        state = ProjectState(series_title="Test", workdir=str(tmp_path))
        storage.save(state)
        storage.save(state)
        # Corrupt both
        (tmp_path / "state.json").write_text("bad", encoding="utf-8")
        (tmp_path / "state.json.bak").write_text("bad", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="novel_forge.storage"):
            loaded = storage.load()
        assert loaded.series_title == ""
        assert "Failed to load state file; attempting backup" in caplog.text
        assert "Failed to load state backup; using default state" in caplog.text

    def test_planned_status_roundtrips(self, tmp_path):
        storage = StateStorage(tmp_path)
        state = ProjectState(series_title="Test", workdir=str(tmp_path), status="企画済")
        storage.save(state)

        loaded = storage.load()

        assert loaded.status == "企画済"


class TestBlackboardStorage:
    def test_roundtrip(self, tmp_path):
        storage = BlackboardStorage(tmp_path)
        bb = Blackboard(scene_summaries={"1": "summary"})
        storage.save(bb)
        loaded = storage.load()
        assert loaded.scene_summaries["1"] == "summary"


class TestBibleStorage:
    def test_roundtrip(self, tmp_path):
        storage = BibleStorage(tmp_path)
        bible = Bible(characters=[CharacterProfile(name="Hero")])
        storage.save(bible)
        loaded = storage.load()
        assert len(loaded.characters) == 1
        assert loaded.characters[0].name == "Hero"
