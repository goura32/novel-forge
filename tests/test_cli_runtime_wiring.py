from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from typer.testing import CliRunner

from novel_forge import cli
from novel_forge.runtime import RunRepository
from novel_forge.workflow_runtime import RuntimeWorkflow
from novel_forge.workflow_task_runner import make_task_runner


@dataclass
class _LLMConfig:
    model: str = "fake"


@dataclass
class _Config:
    workdir: Path
    llm: _LLMConfig = field(default_factory=_LLMConfig)

    def resolve_workdir(self, requested: Path) -> Path:
        assert requested == self.workdir
        return self.workdir


def _bootstrap(repo: RunRepository, slug: str) -> str:
    run = repo.create_run(command="plan", model="fake", verbose=False)
    workflow = RuntimeWorkflow(repo, run, task_runner=lambda _task, _values: {})
    return workflow.bootstrap_plan(
        slug=slug,
        plan={"title": "テスト", "slug": slug, "planned_volumes": [{"number": 1, "title": "第1巻"}]},
        canon_seed={"schema_version": 2, "series": {"id": "series", "title": "テスト", "logline": ""}},
    ).selection_snapshot_id


def test_find_existing_series_uses_runtime_ledger_without_legacy_plan(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    _bootstrap(repo, "series_a")

    assert cli._find_existing_series(tmp_path) == tmp_path / "series_a"


def test_design_command_starts_from_current_selection_snapshot(tmp_path: Path, monkeypatch) -> None:
    repo = RunRepository(tmp_path)
    expected_snapshot_id = _bootstrap(repo, "series_a")
    captured: dict[str, Any] = {}

    class FakeWorkflow:
        def __init__(self, run) -> None:
            self.task_runner = self._task_runner
            captured["input_snapshot_id"] = run.manifest.input_snapshot_id

        @staticmethod
        def load_canon() -> Any:
            return SimpleNamespace(model_dump=lambda **_kwargs: {"schema_version": 2})

        @staticmethod
        def _task_runner(task_id: str, values: dict[str, Any]) -> dict[str, Any]:
            assert task_id == "design.volume.generate"
            assert values["series_plan"]["slug"] == "series_a"
            return {"title": "第1巻", "premise": "開始", "chapters": []}

        @staticmethod
        def publish_design(volume: int, design: dict[str, Any]) -> None:
            assert volume == 1
            assert design["title"] == "第1巻"

    monkeypatch.setattr(cli.RuntimeConfig, "load", staticmethod(lambda: _Config(tmp_path)))
    monkeypatch.setattr(cli, "_make_workflow", lambda repo, run, *_args: FakeWorkflow(run))

    result = CliRunner().invoke(cli.app, ["design", "--workdir", str(tmp_path), "--series", "series_a"])

    assert result.exit_code == 0, result.output
    assert captured["input_snapshot_id"] == expected_snapshot_id


def test_task_runner_dispatches_design_volume_with_registry_variables() -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def complete_json(self, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"title": "第1巻", "premise": "開始", "chapters": []}

    class FakePromptManager:
        def render_task(self, task_id: str, variables: dict[str, str]) -> str:
            captured["task_id"] = task_id
            captured["variables"] = variables
            return "prompt"

    result = make_task_runner(cast(Any, FakeClient()), cast(Any, FakePromptManager()))(
        "design.volume.generate",
        {
            "series_plan": {"title": "テスト"},
            "volume_number": 1,
            "volume_title": "第1巻",
            "genre": ["fantasy"],
            "previous_design": None,
            "bible": {"schema_version": 2},
        },
    )

    assert result["title"] == "第1巻"
    assert captured["task_id"] == "design.volume.generate"
    assert captured["variables"]["volume_number"] == "1"


def test_list_reads_selected_plan_artifact_without_legacy_plan(tmp_path: Path, monkeypatch) -> None:
    repo = RunRepository(tmp_path)
    _bootstrap(repo, "series_a")
    monkeypatch.setattr(cli.RuntimeConfig, "load", staticmethod(lambda: _Config(tmp_path)))

    result = CliRunner().invoke(cli.app, ["list", "--workdir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "series_a" in result.output
    assert "テスト" in result.output
    assert "snapshot-managed" in result.output
