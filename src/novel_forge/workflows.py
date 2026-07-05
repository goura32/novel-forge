"""Workflow wrappers for future orchestration extraction."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class DesignWorkflow:
    def __init__(self, run_design: Callable[[Any, int | None], dict[str, Any]]):
        self._run_design = run_design

    def run(self, engine: Any, volume_number: int | None = None) -> dict[str, Any]:
        return self._run_design(engine, volume_number)


class WriteWorkflow:
    def __init__(self, run_write: Callable[[Any, int | None], list[dict[str, Any]]]):
        self._run_write = run_write

    def run(self, engine: Any, volume_number: int | None = None) -> list[dict[str, Any]]:
        return self._run_write(engine, volume_number)
