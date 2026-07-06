"""Tests for character name registry fallback logging."""

from __future__ import annotations

import logging

from novel_forge.name_registry import load_used_names, record_names


def test_roundtrip_used_names(tmp_path):
    record_names(tmp_path, {"Alice", "Bob"})

    assert load_used_names(tmp_path) == {"Alice", "Bob"}


def test_corrupt_used_names_returns_empty_with_warning(tmp_path, caplog):
    (tmp_path / "used_names.json").write_text("not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="novel_forge.name_registry"):
        names = load_used_names(tmp_path)

    assert names == set()
    assert "Failed to load used character names" in caplog.text
