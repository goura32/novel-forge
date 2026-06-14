
from novel_tool.prompts.loader import PromptLoader
from novel_tool.prompts.renderer import render_template


def test_loads_prompt_from_root(tmp_path):
    root = tmp_path / "prompts"
    (root / "series").mkdir(parents=True)
    (root / "series" / "plan_series.md").write_text("Hello {{name}}", encoding="utf-8")
    assert PromptLoader(root).load("series/plan_series.md") == "Hello {{name}}"


def test_renderer_replaces_placeholders_and_fails_on_missing():
    assert render_template("{{a}}/{{b}}", {"a": "A", "b": "B"}) == "A/B"
    try:
        render_template("{{missing}}", {})
    except KeyError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("missing placeholder should fail")
