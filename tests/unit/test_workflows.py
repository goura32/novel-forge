"""Unit tests for workflow wrappers."""

from __future__ import annotations

from typing import Any

from novel_forge.workflows import DesignWorkflow, WriteWorkflow


def _record_call(calls: list[tuple[Any, int | None]], engine: Any, volume: int | None, result: Any) -> Any:
    calls.append((engine, volume))
    return result


def test_design_workflow_delegates_to_injected_runner() -> None:
    calls: list[tuple[Any, int | None]] = []
    workflow = DesignWorkflow(lambda engine, volume: _record_call(calls, engine, volume, {"ok": True}))

    result = workflow.run("engine", 2)

    assert result == {"ok": True}
    assert calls == [("engine", 2)]


def test_write_workflow_delegates_to_injected_runner() -> None:
    calls: list[tuple[Any, int | None]] = []
    workflow = WriteWorkflow(lambda engine, volume: _record_call(calls, engine, volume, [{"scene": 1}]))

    result = workflow.run("engine", 1)

    assert result == [{"scene": 1}]
    assert calls == [("engine", 1)]
