"""Packaging/runtime resource tests for prompts and schemas."""

from __future__ import annotations

from novel_forge.prompts import PromptManager
from novel_forge.schemas import list_schemas, validate_schemas


def test_default_prompt_manager_loads_packaged_system_prompt() -> None:
    rendered = PromptManager().render("system.md", {})

    required_fragments = [
        "JSON",
        "JSON文字列の中に生の改行を入れない",
        "文字列値の内部で二重引用符",
        "コードフェンスを含めない",
    ]

    for fragment in required_fragments:
        assert fragment in rendered


def test_default_schema_loader_finds_packaged_schemas() -> None:
    assert validate_schemas() == []
    assert "review" in list_schemas()
    assert "scene_draft" in list_schemas()
