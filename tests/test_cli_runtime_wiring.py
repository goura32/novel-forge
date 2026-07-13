from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from typer.testing import CliRunner

from novel_forge import cli
from novel_forge.config import RuntimeConfig
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
    verbose: bool = False

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



def test_verbose_resolution_prefers_explicit_cli_over_config() -> None:
    config = RuntimeConfig(verbose=True)
    assert cli._resolve_verbose(config, None) is True
    assert cli._resolve_verbose(config, False) is False
    assert cli._resolve_verbose(RuntimeConfig(verbose=False), True) is True


def test_find_existing_series_uses_runtime_ledger_without_legacy_plan(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    _bootstrap(repo, "series_a")

    assert cli._find_existing_series(tmp_path) == tmp_path / "series_a"


def test_design_command_delegates_to_pnca_volume_authoring(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, Any] = {}
    parent = SimpleNamespace(contract=SimpleNamespace(volume_purposes=(SimpleNamespace(ordinal=1),)))
    request = SimpleNamespace(artifact_id="volume_request")

    class FakePNCAWorkflow:
        @staticmethod
        def author_volume(*, run: Any, parent: Any, request: Any, scope_id: str) -> Any:
            captured.update({"input_snapshot_id": run.manifest.input_snapshot_id, "parent": parent, "request": request, "scope_id": scope_id})
            return SimpleNamespace(contract=SimpleNamespace(contract_id="volume_001"))

        @staticmethod
        def accept_volume(**_kwargs: Any) -> Any:
            return SimpleNamespace(selection_snapshot_id="snap_after_volume")

    monkeypatch.setattr(cli.RuntimeConfig, "load", staticmethod(lambda: _Config(tmp_path)))
    monkeypatch.setattr(cli, "_find_existing_series", lambda *_args: tmp_path / "series_a")
    monkeypatch.setattr(RunRepository, "current_snapshot_id", lambda *_args: "snap_current")
    monkeypatch.setattr(cli, "_selected_series_contract", lambda *_args: parent, raising=False)
    monkeypatch.setattr(cli, "stage_volume_request", lambda **_kwargs: request, raising=False)
    monkeypatch.setattr(cli, "_make_pnca_workflow", lambda *_args: FakePNCAWorkflow())

    result = CliRunner().invoke(cli.app, ["design", "--workdir", str(tmp_path), "--series", "series_a"])

    assert result.exit_code == 0, result.output
    assert captured == {"input_snapshot_id": "snap_current", "parent": parent, "request": request, "scope_id": "series_a.volume.001"}


def _legacy_design_command_starts_from_current_selection_snapshot(tmp_path: Path, monkeypatch) -> None:
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
            if task_id == "design.volume.generate":
                assert values["series_plan"]["slug"] == "series_a"
                return {"title": "第1巻", "premise": "開始", "chapters": [{"title": "導入", "purpose": "導入"}]}
            if task_id == "design.chapter.generate":
                return {
                    "title": "導入", "purpose": "導入", "theme": "始動", "emotional_arc": "quiet", "outcome": "覚醒",
                    "scenes": [{"title": "覚醒", "pov": "リィナ", "goal": "状況把握", "conflict": "記憶喪失", "outcome": "案内人と対話", "characters": ["リィナ"], "key_events": ["目覚める"], "setting": "覚醒室"}],
                    "chapter_turning_point": "目覚める", "chapter_hook": "案内人が現れる", "foreshadowing_notes": ["星図"], "subplot_notes": ["記憶喪失"],
                }
            if task_id == "design.scene.generate":
                return {
                    "title": "覚醒", "goal": "状況把握", "conflict": "記憶喪失", "outcome": "案内人と対話", "pov": "リィナ", "characters": ["リィナ"], "key_events": ["目覚める"], "setting": "覚醒室", "hook": "目を開ける", "turning_point": "端末が光る", "emotional_arc": "不安から安堵", "ending_hook": "扉が開く",
                    "canon_patch": {"characters": {"state_updates": [{"character": {"kind": "character", "id": "char_001"}, "current_state": "案内人と対話"}]}},
                }
            raise AssertionError(task_id)

        @staticmethod
        def generate_volume_design(*, volume: int, plan: dict[str, Any]) -> Any:
            assert volume == 1
            assert plan["slug"] == "series_a"
            return SimpleNamespace(selection_snapshot_id="snap-after-design")

        @staticmethod
        def publish_design(volume: int, design: dict[str, Any]) -> None:  # pragma: no cover - retained for API parity
            raise AssertionError("publish_design must not be called directly")

    monkeypatch.setattr(cli.RuntimeConfig, "load", staticmethod(lambda: _Config(tmp_path)))
    monkeypatch.setattr(cli, "_make_workflow", lambda repo, run, *_args: FakeWorkflow(run))

    result = CliRunner().invoke(cli.app, ["design", "--workdir", str(tmp_path), "--series", "series_a"])

    assert result.exit_code == 0, result.output
    assert captured["input_snapshot_id"] == expected_snapshot_id



def test_complete_uses_public_design_boundary_and_series_lock(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    class FakeWorkflow:
        def __init__(self, _run: Any) -> None:
            pass

        @staticmethod
        def _run_task(task_id: str, values: dict[str, Any], *, reason: str) -> tuple[Any, dict[str, Any]]:
            calls.append(task_id)
            assert task_id == "plan.series.generate"
            assert values == {"keywords": "k", "existing_slugs": []}
            assert reason == "generate series plan"
            return SimpleNamespace(manifest=SimpleNamespace(attempt_id="att_plan")), {
                "slug": "series_new", "title": "新作", "planned_volumes": [{"title": "第1巻"}]
            }

        @staticmethod
        def _review_and_revise(_stem: str, candidate: dict[str, Any], attempt: Any, **_kwargs: Any) -> tuple[Any, dict[str, Any]]:
            calls.append("plan_quality_gate")
            return attempt, candidate

        @staticmethod
        def bootstrap_plan(
            *, slug: str, plan: dict[str, Any], canon_seed: dict[str, Any], plan_attempt: Any
        ) -> None:
            calls.append("bootstrap")
            assert slug == plan["slug"]
            assert canon_seed["schema_version"] == 2
            assert plan_attempt.manifest.attempt_id == "att_plan"

        @staticmethod
        def generate_volume_design(*, volume: int, plan: dict[str, Any]) -> None:
            calls.append("generate_volume_design")
            assert volume == 1
            assert plan["slug"] == "series_new"

        @staticmethod
        def publish_design(*_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
            raise AssertionError("complete must not bypass generate_volume_design")

        @staticmethod
        def write_volume(volume: int) -> Any:
            calls.append("write_volume")
            assert volume == 1
            return SimpleNamespace(selection_snapshot_id="snap-write")

        @staticmethod
        def export_volume(volume: int) -> dict[str, str]:
            calls.append("export_volume")
            assert volume == 1
            return {"artifact_id": "artifact-export"}

    monkeypatch.setattr(cli.RuntimeConfig, "load", staticmethod(lambda: _Config(tmp_path)))
    monkeypatch.setattr(cli, "_make_workflow", lambda _repo, run, *_args: FakeWorkflow(run))

    result = CliRunner().invoke(cli.app, ["complete", "k", "--workdir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert calls == [
        "plan.series.generate", "plan_quality_gate", "bootstrap", "generate_volume_design", "write_volume", "export_volume"
    ]
    assert not list((tmp_path / ".novel-forge" / "runtime" / "locks").glob("series-series_new.lock.json"))


def test_export_command_passes_markdown_format_to_workflow(tmp_path: Path, monkeypatch) -> None:
    repo = RunRepository(tmp_path)
    _bootstrap(repo, "series_a")
    captured: dict[str, Any] = {}

    class FakeWorkflow:
        @staticmethod
        def export_volume(volume: int, *, format: str) -> dict[str, str]:
            captured.update({"volume": volume, "format": format})
            return {"artifact_id": "artifact-markdown"}

    monkeypatch.setattr(cli.RuntimeConfig, "load", staticmethod(lambda: _Config(tmp_path)))
    monkeypatch.setattr(cli, "_make_workflow", lambda *_args: FakeWorkflow())

    result = CliRunner().invoke(
        cli.app,
        ["export", "--workdir", str(tmp_path), "--series", "series_a", "--format", "markdown"],
    )

    assert result.exit_code == 0, result.output
    assert captured == {"volume": 1, "format": "markdown"}



def test_plan_command_delegates_root_bootstrap_to_pnca_workflow(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    request = SimpleNamespace(artifact_id="request_artifact")

    class FakePNCAWorkflow:
        @staticmethod
        def author_series(*, run: Any, scope_id: str, request: Any) -> Any:
            calls.append("author")
            assert run.manifest.command == "plan"
            assert scope_id == run.manifest.run_id
            assert request.artifact_id == "request_artifact"
            return SimpleNamespace(contract=SimpleNamespace(contract_id="moon_lantern"))

        @staticmethod
        def accept_series(*, authored: Any) -> Any:
            calls.append("accept")
            assert authored.contract.contract_id == "moon_lantern"
            return SimpleNamespace(selection_snapshot_id="snap-pnca")

    def fake_stage(**kwargs: Any) -> Any:
        calls.append("stage")
        assert kwargs["request_id"] == kwargs["run"].manifest.run_id
        assert kwargs["keywords"] == "月灯りの魔女"
        assert kwargs["existing_slugs"] == ()
        return request

    monkeypatch.setattr(cli.RuntimeConfig, "load", staticmethod(lambda: _Config(tmp_path)))
    monkeypatch.setattr(cli, "stage_series_request", fake_stage, raising=False)
    monkeypatch.setattr(cli, "_make_pnca_workflow", lambda *_args: FakePNCAWorkflow(), raising=False)

    result = CliRunner().invoke(cli.app, ["plan", "月灯りの魔女", "--workdir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert calls == ["stage", "author", "accept"]
    assert "moon_lantern" in result.output
    assert "snap-pnca" in result.output



def test_task_runner_passes_registry_schema_to_llm_client() -> None:
    """Schema validation must not be bypassed: the runner must hand the resolved
    task schema to ``LLMClient.complete_json``."""
    from novel_forge.task_registry import DEFAULT_TASK_REGISTRY

    captured: dict[str, Any] = {}

    class FakeClient:
        def complete_json(self, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"title": "第1巻", "premise": "開始", "chapters": []}

    class FakePromptManager:
        def render_task(self, task_id: str, variables: dict[str, str]) -> str:
            return "prompt"

    make_task_runner(cast(Any, FakeClient()), cast(Any, FakePromptManager()))(
        "design.volume.generate",
        {
            "series_plan": {"title": "テスト"},
            "volume_number": 1,
            "volume_title": "第1巻",
            "genre": ["fantasy"],
            "previous_design": None,
            "canon_context": {"schema_version": 2},
        },
    )

    assert "schema" in captured, "complete_json was called without a schema"
    expected = DEFAULT_TASK_REGISTRY.load_schema("design.volume.generate")
    assert captured["schema"] == expected


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
            "canon_context": {"schema_version": 2},
        },
    )

    assert result["title"] == "第1巻"
    assert captured["task_id"] == "design.volume.generate"
    assert captured["variables"]["volume_number"] == "1"


def test_task_runner_dispatches_design_chapter_and_scene_with_complete_prompt_contracts() -> None:
    calls: list[tuple[str, set[str]]] = []

    class FakeClient:
        def complete_json(self, **_kwargs: Any) -> dict[str, Any]:
            return {}

    class FakePromptManager:
        def render_task(self, task_id: str, variables: dict[str, str]) -> str:
            calls.append((task_id, set(variables)))
            return "prompt"

    runner = make_task_runner(cast(Any, FakeClient()), cast(Any, FakePromptManager()))
    runner(
        "design.chapter.generate",
        {
            "series_plan": {}, "volume_number": 1, "volume_title": "第1巻", "volume_premise": "p",
            "chapter_number": 1, "chapter_title": "第1章", "chapter_purpose": "導入",
            "previous_chapter_outcome": "", "previous_volume_summary": None, "canon_context": {},
        },
    )
    runner(
        "design.scene.generate",
        {
            "series_plan": {}, "volume_number": 1, "volume_title": "第1巻", "volume_premise": "p",
            "chapter_number": 1, "chapter_title": "第1章", "chapter_purpose": "導入",
            "chapter_theme": "t", "chapter_emotional_arc": "a", "chapter_foreshadowing_notes": [],
            "chapter_subplot_notes": [], "scene_number": 1, "scene_count": 1,
            "chapter_scene_number": 1, "chapter_scene_count": 1, "scene_seed": {},
            "previous_outcome": "", "previous_volume_summary": None, "canon_context": {},
            "canon_patch_schema": {},
        },
    )

    assert calls == [
        ("design.chapter.generate", {"series_plan", "volume_number", "volume_title", "volume_premise", "chapter_number", "chapter_title", "chapter_purpose", "previous_chapter_outcome", "previous_volume_summary", "canon_context"}),
        ("design.scene.generate", {"series_plan", "volume_number", "volume_title", "volume_premise", "chapter_number", "chapter_title", "chapter_purpose", "chapter_theme", "chapter_emotional_arc", "chapter_foreshadowing_notes", "chapter_subplot_notes", "scene_number", "scene_count", "chapter_scene_number", "chapter_scene_count", "scene_seed", "previous_outcome", "previous_volume_summary", "canon_context", "canon_patch_schema"}),
    ]


def test_list_reads_selected_plan_artifact_without_legacy_plan(tmp_path: Path, monkeypatch) -> None:
    repo = RunRepository(tmp_path)
    _bootstrap(repo, "series_a")
    monkeypatch.setattr(cli.RuntimeConfig, "load", staticmethod(lambda: _Config(tmp_path)))

    result = CliRunner().invoke(cli.app, ["list", "--workdir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "series_a" in result.output
    assert "テスト" in result.output
    assert "snapshot-managed" in result.output
