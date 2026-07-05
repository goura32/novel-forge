"""Unit tests for LLM task primitives."""

from __future__ import annotations

import pytest

from novel_forge.llm_task import LLMTaskRunner, TaskDefinition, TaskRegistry


class SpyLLM:
    def __init__(self) -> None:
        self.calls = []

    def complete_json(self, kind, system_prompt, user_prompt, schema, seed_offset=0):
        self.calls.append((kind, system_prompt, user_prompt, schema, seed_offset))
        return {"ok": True}


def test_task_registry_rejects_duplicate_names() -> None:
    registry = TaskRegistry()
    task = TaskDefinition("scene_design", "scene_design.md", "scene_design")

    registry.register(task)

    with pytest.raises(ValueError):
        registry.register(task)


def test_llm_task_runner_renders_prompt_and_loads_schema() -> None:
    llm = SpyLLM()
    task = TaskDefinition("scene_design", "scene_design.md", "scene_design")
    runner = LLMTaskRunner(
        llm=llm,
        prompt_renderer=lambda name, vars: f"{name}:{vars['title']}",
        schema_loader=lambda name: {"schema": name},
        system_prompt="system",
    )

    result = runner.run(task, {"title": "出会い"}, seed_offset=3)

    assert result == {"ok": True}
    assert llm.calls == [("scene_design", "system", "scene_design.md:出会い", {"schema": "scene_design"}, 3)]
