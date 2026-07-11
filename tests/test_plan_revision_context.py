from __future__ import annotations

import importlib
from types import SimpleNamespace

plan = importlib.import_module("novel_forge.engine.plan")


class CapturingPrompts:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def render(self, name: str, values: dict) -> str:
        self.calls.append((name, values))
        return name


class FakeLLM:
    def complete_json(self, kind: str, system: str, prompt: str, schema: dict | None = None, seed_offset: int = 0) -> dict:
        if kind == "series_plan_characters":
            return {"main_characters": []}
        if kind == "series_plan_volumes":
            return {"planned_volumes": []}
        return {"issues": []}


def _engine(prompts: CapturingPrompts) -> SimpleNamespace:
    return SimpleNamespace(_prompts=prompts, _llm=FakeLLM(), _quality=None, _lang="ja")


def test_plan_characters_revision_receives_series_concept_context(monkeypatch) -> None:
    prompts = CapturingPrompts()
    concept = {"title": "深淵法廷", "logline": "海底都市の法廷ミステリ"}

    def fake_generate_and_review(*, revise_fn, **kwargs):
        revise_fn({"main_characters": []}, {"issues": []}, "system", 0)
        return {"main_characters": []}, {"issues": []}

    monkeypatch.setattr(plan, "generate_and_review", fake_generate_and_review)

    plan._generate_plan_characters(_engine(prompts), concept, "system", set())

    revision_values = [values for name, values in prompts.calls if name == "plan_characters_revise.md"][-1]
    assert "深淵法廷" in revision_values["concept_text"]
    assert "海底都市の法廷ミステリ" in revision_values["concept_text"]


def test_plan_volumes_revision_receives_series_concept_context(monkeypatch) -> None:
    prompts = CapturingPrompts()
    concept = {"title": "深淵法廷", "logline": "海底都市の法廷ミステリ", "world_summary": "深海都市"}
    characters = {"main_characters": [{"name": "キア", "role": "鑑定士", "arc": "真実を選ぶ"}]}

    def fake_generate_and_review(*, revise_fn, **kwargs):
        revise_fn({"planned_volumes": []}, {"issues": []}, "system", 0)
        return {"planned_volumes": []}, {"issues": []}

    monkeypatch.setattr(plan, "generate_and_review", fake_generate_and_review)

    plan._generate_plan_volumes(_engine(prompts), concept, characters, "system")

    revision_values = [values for name, values in prompts.calls if name == "plan_volumes_revise.md"][-1]
    assert "深淵法廷" in revision_values["concept_text"]
    assert "海底都市の法廷ミステリ" in revision_values["concept_text"]
    assert "深海都市" in revision_values["concept_text"]
