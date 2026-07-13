"""Production PNCA task specifications backed by packaged resources."""

from __future__ import annotations

from hashlib import sha256
from importlib import resources

from novel_forge.pnca.registry import ArtifactSpec, InputBinding, PNCATaskRegistry, TaskSpec


def _resource_digest(name: str, suffix: str) -> str:
    raw = (resources.files("novel_forge") / "resources" / name / suffix).read_bytes()
    return f"sha256:{sha256(raw).hexdigest()}"


def default_pnca_task_registry() -> PNCATaskRegistry:
    """Return the production allow-list; no task is inferred from filenames."""
    return PNCATaskRegistry(
        specs=(
            TaskSpec(
                task_id="pnca.series.contract",
                task_kind="authoring",
                input_bindings=(InputBinding(role="series.request", variable="request"),),
                output=ArtifactSpec(
                    role="series.contract.proposal",
                    artifact_type="pnca.series.contract.proposal",
                    logical_key_template="pnca.series.contract.proposal.{scope_id}",
                ),
                prompt_digest=_resource_digest("prompts", "pnca_series_contract.md"),
                schema_digest=_resource_digest("schemas", "pnca_series_contract.json"),
                model_profile="default",
                max_input_bytes=16_384,
                max_output_bytes=65_536,
                idempotency_scope="series-contract",
            ),
            TaskSpec(
                task_id="pnca.volume.contract",
                task_kind="authoring",
                input_bindings=(
                    InputBinding(role="parent.contract", variable="parent"),
                    InputBinding(role="volume.request", variable="request"),
                ),
                output=ArtifactSpec(
                    role="volume.contract.proposal",
                    artifact_type="pnca.volume.contract.proposal",
                    logical_key_template="pnca.volume.contract.proposal.{scope_id}",
                ),
                prompt_digest=_resource_digest("prompts", "pnca_volume_contract.md"),
                schema_digest=_resource_digest("schemas", "pnca_volume_contract.json"),
                model_profile="default",
                max_input_bytes=16_384,
                max_output_bytes=65_536,
                idempotency_scope="volume-contract",
            ),
            TaskSpec(
                task_id="pnca.chapter.contract",
                task_kind="authoring",
                input_bindings=(
                    InputBinding(role="parent.contract", variable="parent"),
                    InputBinding(role="chapter.request", variable="request"),
                ),
                output=ArtifactSpec(
                    role="chapter.contract.proposal",
                    artifact_type="pnca.chapter.contract.proposal",
                    logical_key_template="pnca.chapter.contract.proposal.{scope_id}",
                ),
                prompt_digest=_resource_digest("prompts", "pnca_chapter_contract.md"),
                schema_digest=_resource_digest("schemas", "pnca_chapter_contract.json"),
                model_profile="default",
                max_input_bytes=16_384,
                max_output_bytes=65_536,
                idempotency_scope="chapter-contract",
            ),
            TaskSpec(
                task_id="pnca.scene.contract",
                task_kind="authoring",
                input_bindings=(
                    InputBinding(role="parent.contract", variable="parent"),
                    InputBinding(role="canon.frontier", variable="frontier"),
                    InputBinding(role="canon.projection", variable="canon_projection"),
                    InputBinding(role="scene.request", variable="request"),
                ),
                output=ArtifactSpec(
                    role="scene.contract.proposal",
                    artifact_type="pnca.scene.contract.proposal",
                    logical_key_template="pnca.scene.contract.proposal.{scope_id}",
                ),
                prompt_digest=_resource_digest("prompts", "pnca_scene_contract.md"),
                schema_digest=_resource_digest("schemas", "pnca_scene_contract.json"),
                model_profile="default",
                max_input_bytes=65_536,
                max_output_bytes=65_536,
                idempotency_scope="scene-contract",
            ),
            TaskSpec(
                task_id="pnca.writer_view.review",
                task_kind="audit",
                input_bindings=(InputBinding(role="writer.view", variable="writer_view"),),
                output=ArtifactSpec(
                    role="writer.view.review",
                    artifact_type="pnca.writer_view.review",
                    logical_key_template="pnca.writer_view.review.{scope_id}",
                ),
                prompt_digest=_resource_digest("prompts", "pnca_writer_view_review.md"),
                schema_digest=_resource_digest("schemas", "review_issues.json"),
                model_profile="default",
                max_input_bytes=32_768,
                max_output_bytes=16_384,
                idempotency_scope="writer-view-review",
            ),
            TaskSpec(
                task_id="pnca.writer_view.revise",
                task_kind="authoring",
                input_bindings=(
                    InputBinding(role="writer.view", variable="writer_view"),
                    InputBinding(role="writer.view.review", variable="issues"),
                ),
                output=ArtifactSpec(
                    role="writer.view.revised",
                    artifact_type="pnca.writer_view",
                    logical_key_template="pnca.writer_view.revised.{scope_id}",
                ),
                prompt_digest=_resource_digest("prompts", "pnca_writer_view_revise.md"),
                schema_digest=_resource_digest("schemas", "pnca_writer_view_revise.json"),
                model_profile="default",
                max_input_bytes=32_768,
                max_output_bytes=32_768,
                idempotency_scope="writer-view-revise",
            ),
            TaskSpec(
                task_id="pnca.scene.render",
                task_kind="render",
                input_bindings=(InputBinding(role="writer.view", variable="writer_view"),),
                output=ArtifactSpec(
                    role="scene.draft",
                    artifact_type="pnca.scene_draft",
                    logical_key_template="pnca.scene_draft.{scope_id}",
                ),
                prompt_digest=_resource_digest("prompts", "pnca_scene_render.md"),
                schema_digest=_resource_digest("schemas", "pnca_scene_render.json"),
                model_profile="default",
                max_input_bytes=32_768,
                max_output_bytes=65_536,
                idempotency_scope="scene-render",
            ),
            TaskSpec(
                task_id="pnca.scene.revise",
                task_kind="render",
                input_bindings=(
                    InputBinding(role="writer.view", variable="writer_view"),
                    InputBinding(role="scene.draft", variable="draft"),
                    InputBinding(role="draft.audit", variable="issues"),
                ),
                output=ArtifactSpec(role="scene.draft.revised", artifact_type="pnca.scene_draft", logical_key_template="pnca.scene_draft.revised.{scope_id}"),
                prompt_digest=_resource_digest("prompts", "pnca_scene_revise.md"),
                schema_digest=_resource_digest("schemas", "pnca_scene_revise.json"),
                model_profile="default", max_input_bytes=65_536, max_output_bytes=65_536,
                idempotency_scope="scene-revise",
            ),
            TaskSpec(
                task_id="pnca.draft.audit",
                task_kind="audit",
                input_bindings=(
                    InputBinding(role="writer.view", variable="writer_view"),
                    InputBinding(role="scene.draft", variable="draft"),
                ),
                output=ArtifactSpec(
                    role="draft.audit",
                    artifact_type="pnca.draft_audit",
                    logical_key_template="pnca.draft_audit.{scope_id}",
                ),
                prompt_digest=_resource_digest("prompts", "pnca_draft_audit.md"),
                schema_digest=_resource_digest("schemas", "pnca_draft_audit.json"),
                model_profile="default",
                max_input_bytes=65_536,
                max_output_bytes=16_384,
                idempotency_scope="draft-audit",
            ),

        )
    )
