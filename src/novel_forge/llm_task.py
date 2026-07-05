"""Reusable LLM task execution primitives."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskDefinition:
    name: str
    prompt_name: str
    schema_name: str


class TaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskDefinition] = {}

    def register(self, task: TaskDefinition) -> None:
        if task.name in self._tasks:
            raise ValueError(f"Task already registered: {task.name}")
        self._tasks[task.name] = task

    def get(self, name: str) -> TaskDefinition:
        try:
            return self._tasks[name]
        except KeyError as exc:
            raise KeyError(f"Task not registered: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._tasks)


class LLMTaskRunner:
    def __init__(self, llm: Any, prompt_renderer: Callable[[str, dict[str, str]], str], schema_loader: Callable[[str], dict[str, Any]], system_prompt: str) -> None:
        self._llm = llm
        self._prompt_renderer = prompt_renderer
        self._schema_loader = schema_loader
        self._system_prompt = system_prompt

    def run(self, task: TaskDefinition, variables: dict[str, str], seed_offset: int = 0) -> dict[str, Any]:
        user_prompt = self._prompt_renderer(task.prompt_name, variables)
        schema = self._schema_loader(task.schema_name)
        return self._llm.complete_json(task.name, self._system_prompt, user_prompt, schema, seed_offset=seed_offset)
