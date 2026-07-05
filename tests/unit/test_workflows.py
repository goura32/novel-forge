"""Unit tests for workflow wrappers."""

from __future__ import annotations

from novel_forge.workflows import DesignWorkflow, WriteWorkflow


def test_design_workflow_delegates_to_injected_runner() -> None:
    calls = []
    workflow = DesignWorkflow(lambda engine, volume: calls.append((engine, volume)) or {"ok": True})

    result = workflow.run("engine", 2)

    assert result == {"ok": True}
    assert calls == [("engine", 2)]


def test_write_workflow_delegates_to_injected_runner() -> None:
    calls = []
    workflow = WriteWorkflow(lambda engine, volume: calls.append((engine, volume)) or [{"scene": 1}])

    result = workflow.run("engine", 1)

    assert result == [{"scene": 1}]
    assert calls == [("engine", 1)]
