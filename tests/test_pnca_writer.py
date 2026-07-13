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


def test_renderer_passes_only_writer_view_and_persists_draft(tmp_path) -> None:
    observed = {}

    def provider(task_id, projection, operation_key):
        observed["task_id"] = task_id
        observed["projection"] = projection
        observed["operation_key"] = operation_key
        return {"content": "夜明け前、リナは塔へ向かった。"}

    registry = PNCATaskRegistry(specs=(
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
    assert repo.read_payload(rendered.draft) == {"content": "夜明け前、リナは塔へ向かった。"}
