"""Tests for prompts.py — render_prompt uses {key} (single-brace) placeholders."""

import pytest

from novel_forge.prompts import PromptManager, render_prompt


class TestRenderPrompt:
    def test_basic_replacement(self):
        result = render_prompt("Hello {name}", {"name": "World"})
        assert result == "Hello World"

    def test_multiple_replacements(self):
        result = render_prompt("{a} and {b}", {"a": "Alpha", "b": "Beta"})
        assert result == "Alpha and Beta"

    def test_no_placeholders(self):
        result = render_prompt("plain text", {})
        assert result == "plain text"

    def test_empty_template(self):
        result = render_prompt("", {})
        assert result == ""

    def test_longer_key_first(self):
        """Longer keys should be replaced before shorter ones to avoid partial matches."""
        result = render_prompt("{name} {name_long}", {"name": "A", "name_long": "B"})
        assert result == "A B"

    def test_japanese_variables(self):
        result = render_prompt("{lang} で出力", {"lang": "ja"})
        assert result == "ja で出力"

    def test_repeated_placeholder(self):
        result = render_prompt("{x} {x}", {"x": "same"})
        assert result == "same same"
    def test_inserted_value_is_not_reinterpreted_as_a_placeholder(self):
        result = render_prompt("request={request}\nschema={schema}", {"request": '{"keywords":"{schema}"}', "schema": "SPEC"})
        assert result == 'request={"keywords":"{schema}"}\nschema=SPEC'


class TestPromptManager:
    def test_render_loads_and_renders(self, tmp_path):
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "test.md").write_text("{greeting} {name}", encoding="utf-8")

        mgr = PromptManager(prompt_dir=prompt_dir)
        result = mgr.render("test.md", {"greeting": "こんにちは", "name": "世界"})
        assert result == "こんにちは 世界"

    def test_render_missing_file_raises(self, tmp_path):
        mgr = PromptManager(prompt_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            mgr.render("nonexistent.md", {})
