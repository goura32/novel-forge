"""PNCA writer boundary tests."""

from __future__ import annotations

from novel_forge.pnca.contracts import WriterView
from novel_forge.pnca.registry import (
    ArtifactSpec,
    InputBinding,
    PNCATaskExecutor,
    PNCATaskRegistry,
    TaskSpec,
)
from novel_forge.pnca.writer import PNCARenderer
from novel_forge.runtime import RunRepository


def _coverage_spec() -> TaskSpec:
    return TaskSpec(
        task_id="pnca.scene.coverage", task_kind="audit",
        input_bindings=(InputBinding(role="writer.view", variable="writer_view"), InputBinding(role="scene.draft", variable="draft")),
        output=ArtifactSpec(role="scene.coverage", artifact_type="pnca.draft_coverage", logical_key_template="coverage.{scope_id}"),
        prompt_digest="sha256:prompt", schema_digest="sha256:schema", model_profile="test",
        max_input_bytes=4096, max_output_bytes=4096, idempotency_scope="scene-coverage",
    )


def test_renderer_passes_only_writer_view_and_persists_draft(tmp_path) -> None:
    observed = {}

    def provider(task_id, projection, operation_key):
        if task_id == "pnca.writer_view.review":
            return {"issues": []}
        if task_id == "pnca.scene.coverage":
            return {"evidence": [{"obligation": "end_constraint", "draft_quote": "リナは塔へ向かった。"}]}
        observed["task_id"] = task_id
        observed["projection"] = projection
        observed["operation_key"] = operation_key
        return {"content": "夜明け前、リナは塔へ向かった。", "coverage": {"evidence": [{"obligation": "end_constraint", "draft_quote": "リナは塔へ向かった。"}]}}

    registry = PNCATaskRegistry(specs=(
        TaskSpec(
            task_id="pnca.writer_view.review",
            task_kind="audit",
            input_bindings=(InputBinding(role="writer.view", variable="writer_view"),),
            output=ArtifactSpec(role="writer.view.review", artifact_type="pnca.writer_view.review", logical_key_template="pnca.writer_view.review.{scope_id}"),
            prompt_digest="sha256:prompt",
            schema_digest="sha256:schema",
            model_profile="test",
            max_input_bytes=4096,
            max_output_bytes=4096,
            idempotency_scope="writer-view-review",
        ),
        TaskSpec(
            task_id="pnca.scene.render",
            task_kind="render",
            input_bindings=(InputBinding(role="writer.view", variable="writer_view"),),
            output=ArtifactSpec(role="scene.draft", artifact_type="pnca.scene_draft", logical_key_template="pnca.scene_draft.{scope_id}"),
            prompt_digest="sha256:prompt",
            schema_digest="sha256:schema",
            model_profile="test",
            max_input_bytes=4096,
            max_output_bytes=4096,
            idempotency_scope="scene",
        ),
        _coverage_spec(),
    ))
    executor = PNCATaskExecutor(registry=registry, provider=provider)
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)
    view = WriterView(
        start_context={"pov": "リナ"},
        narrative_contract={"goal": "塔へ行く"},
        end_constraints={"location": "塔"},
        presentation_constraints={"voice": "三人称"},
    )

    rendered = PNCARenderer(repo).render(
        run=run,
        scene_contract_artifact_id="art_scene_contract",
        scene_contract_digest="sha256:scene",
        view=view,
        executor=executor,
        scope_id="scene_001",
    )

    assert observed["task_id"] == "pnca.scene.render"
    assert set(observed["projection"]) == {"writer_view"}
    assert "canon" not in str(observed["projection"])
    assert repo.read_payload(rendered.draft) == {
        "content": "夜明け前、リナは塔へ向かった。",
        "coverage": {"evidence": [{"obligation": "end_constraint", "beat_index": None, "draft_quote": "リナは塔へ向かった。"}]},
    }


def test_renderer_regenerates_when_obligation_coverage_is_invalid(tmp_path) -> None:
    coverage_calls = 0

    def provider(task_id, projection, operation_key):
        nonlocal coverage_calls
        if task_id == "pnca.writer_view.review":
            return {"issues": []}
        if task_id == "pnca.scene.render":
            return {"content": "リナは塔の扉に手を置いた。"}
        assert task_id == "pnca.scene.coverage"
        coverage_calls += 1
        if coverage_calls == 1:
            return {"evidence": []}
        return {"evidence": [{"obligation": "required_beat", "beat_index": 0, "draft_quote": "リナは塔の扉に手を置いた。"}, {"obligation": "end_constraint", "draft_quote": "リナは塔の扉に手を置いた。"}]}

    registry = PNCATaskRegistry(specs=(
        TaskSpec(task_id="pnca.writer_view.review", task_kind="audit", input_bindings=(InputBinding(role="writer.view", variable="writer_view"),), output=ArtifactSpec(role="writer.view.review", artifact_type="pnca.writer_view.review", logical_key_template="review.{scope_id}"), prompt_digest="sha256:prompt", schema_digest="sha256:schema", model_profile="test", max_input_bytes=4096, max_output_bytes=4096, idempotency_scope="writer-view-review"),
        TaskSpec(task_id="pnca.scene.render", task_kind="render", input_bindings=(InputBinding(role="writer.view", variable="writer_view"),), output=ArtifactSpec(role="scene.draft", artifact_type="pnca.scene_draft", logical_key_template="draft.{scope_id}"), prompt_digest="sha256:prompt", schema_digest="sha256:schema", model_profile="test", max_input_bytes=4096, max_output_bytes=4096, idempotency_scope="scene-render"),
        _coverage_spec(),
    ))
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)

    rendered = PNCARenderer(repo).render(
        run=run,
        scene_contract_artifact_id="art_scene_contract",
        scene_contract_digest="sha256:scene",
        view=WriterView(required_beats=("リナが塔の扉に手を置く",), end_constraints={"visible_end": "リナが塔の扉に手を置く"}),
        executor=PNCATaskExecutor(registry=registry, provider=provider),
        scope_id="scene_coverage",
    )

    assert coverage_calls == 2
    assert repo.read_payload(rendered.draft)["coverage"]["evidence"][0]["beat_index"] == 0


def test_renderer_preserves_writer_view_review_as_observation_without_a_revision_loop(tmp_path) -> None:
    calls: list[str] = []

    def provider(task_id, projection, operation_key):
        calls.append(task_id)
        if task_id == "pnca.writer_view.review":
            if len([call for call in calls if call == task_id]) == 1:
                return {"issues": [{"field": "end_constraints", "severity": "critical", "description": "POV外の内面を要求している", "suggestion": "POVが見える動作だけにする"}]}
            return {"issues": []}
        if task_id == "pnca.writer_view.revise":
            return {"writer_view": {"start_context": {"pov": "リナ"}, "narrative_contract": {"goal": "塔へ行く"}, "end_constraints": {"visible_end": "リナが塔の扉に手を置く"}, "presentation_constraints": {"voice": "三人称限定"}, "required_beats": ["リナが塔の扉に手を置く"]}}
        if task_id == "pnca.scene.render":
            return {"content": "リナは塔の扉に手を置いた。"}
        assert task_id == "pnca.scene.coverage"
        return {"evidence": [{"obligation": "end_constraint", "draft_quote": "リナは塔の扉に手を置いた。"}]}

    registry = PNCATaskRegistry(specs=(
        TaskSpec(task_id="pnca.writer_view.review", task_kind="audit", input_bindings=(InputBinding(role="writer.view", variable="writer_view"),), output=ArtifactSpec(role="writer.view.review", artifact_type="pnca.writer_view.review", logical_key_template="review.{scope_id}"), prompt_digest="sha256:prompt", schema_digest="sha256:schema", model_profile="test", max_input_bytes=4096, max_output_bytes=4096, idempotency_scope="writer-view-review"),
        TaskSpec(task_id="pnca.writer_view.revise", task_kind="authoring", input_bindings=(InputBinding(role="writer.view", variable="writer_view"), InputBinding(role="writer.view.review", variable="issues")), output=ArtifactSpec(role="writer.view.revised", artifact_type="pnca.writer_view", logical_key_template="revise.{scope_id}"), prompt_digest="sha256:prompt", schema_digest="sha256:schema", model_profile="test", max_input_bytes=4096, max_output_bytes=4096, idempotency_scope="writer-view-revise"),
        TaskSpec(task_id="pnca.scene.render", task_kind="render", input_bindings=(InputBinding(role="writer.view", variable="writer_view"),), output=ArtifactSpec(role="scene.draft", artifact_type="pnca.scene_draft", logical_key_template="draft.{scope_id}"), prompt_digest="sha256:prompt", schema_digest="sha256:schema", model_profile="test", max_input_bytes=4096, max_output_bytes=4096, idempotency_scope="scene-render"),
        _coverage_spec(),
    ))
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)

    rendered = PNCARenderer(repo).render(
        run=run,
        scene_contract_artifact_id="art_scene_contract",
        scene_contract_digest="sha256:scene",
        view=WriterView(end_constraints={"invalid": "相手が内心で受け入れる"}),
        executor=PNCATaskExecutor(registry=registry, provider=provider),
        scope_id="scene_001",
    )

    assert calls == ["pnca.writer_view.review", "pnca.scene.render", "pnca.scene.coverage"]
    assert repo.read_payload(rendered.writer_view)["end_constraints"] == {"invalid": "相手が内心で受け入れる"}
