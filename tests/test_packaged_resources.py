"""Packaging/runtime resource tests for prompts and schemas."""

from __future__ import annotations

from novel_forge.prompts import PromptManager
from novel_forge.schemas import list_schemas, validate_schemas


def test_default_prompt_manager_loads_packaged_system_prompt() -> None:
    rendered = PromptManager().render("system.md", {})

    assert "共通システム指示" in rendered
    assert "JSON" in rendered


def test_default_schema_loader_finds_packaged_schemas() -> None:
    assert validate_schemas() == []
    assert "review" in list_schemas()
    assert "scene_draft" in list_schemas()
