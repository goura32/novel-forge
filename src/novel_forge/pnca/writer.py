"""PNCA prose rendering boundary."""

from __future__ import annotations

from dataclasses import dataclass

from novel_forge.pnca.contracts import DraftAudit, WriterView
from novel_forge.pnca.registry import PNCATaskExecutor
from novel_forge.pnca.validation import PNCAStructuralError, validate_writer_view
from novel_forge.runtime import ArtifactReference, RunHandle, RunRepository


@dataclass(frozen=True, slots=True)
class RenderedDraft:
    writer_view: ArtifactReference
    draft: ArtifactReference


class PNCARenderer:
    """Persist a WriterView and its prose draft without a summary handoff."""

    def __init__(self, repository: RunRepository) -> None:
        self.repository = repository

    def render(
        self,
        *,
        run: RunHandle,
        scene_contract_artifact_id: str,
        scene_contract_digest: str,
        view: WriterView,
        executor: PNCATaskExecutor,
        scope_id: str,
    ) -> RenderedDraft:
        validate_writer_view(view)
        writer_attempt = self.repository.start_attempt(
            run, task_id="pnca.scene.writer_view", phase="write", reason="compile writer view"
        )
        writer_view = self.repository.commit_artifact(
            writer_attempt,
            artifact_type="pnca.writer_view",
            logical_key=f"pnca.writer_view.{scope_id}",
            payload=view.model_dump(mode="json"),
            payload_name="writer_view.json",
            input_artifact_ids=(scene_contract_artifact_id,),
            metadata={"scene_contract_digest": scene_contract_digest},
        )
        result = executor.execute(
            task_id="pnca.scene.render",
            artifacts={"writer.view": view.model_dump(mode="json")},
            input_artifact_ids=(writer_view.artifact_id,),
            scope_id=scope_id,
        )
        content = result.get("content") if isinstance(result, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise PNCAStructuralError("PNCA render output requires non-empty content")
        draft_attempt = self.repository.start_attempt(
            run, task_id="pnca.scene.render", phase="write", reason="render scene draft"
        )
        draft = self.repository.commit_artifact(
            draft_attempt,
            artifact_type="pnca.scene_draft",
            logical_key=f"pnca.scene_draft.{scope_id}",
            payload={"content": content},
            payload_name="draft.json",
            input_artifact_ids=(writer_view.artifact_id,),
        )
        return RenderedDraft(writer_view=writer_view, draft=draft)

    def audit(
        self,
        *,
        run: RunHandle,
        scene_contract_artifact_id: str,
        writer_view: WriterView,
        writer_view_artifact_id: str,
        draft: ArtifactReference,
        executor: PNCATaskExecutor,
        scope_id: str,
    ) -> ArtifactReference:
        """Review a rendered draft against its WriterView; returns the draft audit artifact."""
        result = executor.execute(
            task_id="pnca.draft.audit",
            artifacts={
                "writer.view": writer_view.model_dump(mode="json"),
                "scene.draft": self.repository.read_payload(draft),
            },
            input_artifact_ids=(writer_view_artifact_id, draft.artifact_id),
            scope_id=scope_id,
        )
        try:
            audit_payload = DraftAudit.model_validate(result)
        except ValueError as exc:
            raise PNCAStructuralError(f"PNCA draft audit output is invalid: {exc}") from exc
        audit_attempt = self.repository.start_attempt(
            run, task_id="pnca.draft.audit", phase="write", reason="audit scene draft"
        )
        audit = self.repository.commit_artifact(
            audit_attempt,
            artifact_type="pnca.draft_audit",
            logical_key=f"pnca.draft_audit.{scope_id}",
            payload=audit_payload.model_dump(mode="json"),
            payload_name="draft_audit.json",
            input_artifact_ids=(scene_contract_artifact_id, writer_view_artifact_id, draft.artifact_id),
        )
        return audit

    def revise(
        self, *, run: RunHandle, writer_view: WriterView, writer_view_artifact_id: str,
        draft: ArtifactReference, audit: ArtifactReference, executor: PNCATaskExecutor, scope_id: str
    ) -> ArtifactReference:
        result = executor.execute(
            task_id="pnca.scene.revise",
            artifacts={"writer.view": writer_view.model_dump(mode="json"), "scene.draft": self.repository.read_payload(draft), "draft.audit": self.repository.read_payload(audit)},
            input_artifact_ids=(writer_view_artifact_id, draft.artifact_id, audit.artifact_id), scope_id=scope_id,
        )
        content = result.get("content") if isinstance(result, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise PNCAStructuralError("PNCA revision output requires non-empty content")
        attempt = self.repository.start_attempt(run, task_id="pnca.scene.revise", phase="write", reason="resolve draft audit issues")
        return self.repository.commit_artifact(
            attempt, artifact_type="pnca.scene_draft", logical_key=f"pnca.scene_draft.revised.{scope_id}",
            payload={"content": content}, payload_name="draft.json",
            input_artifact_ids=(writer_view_artifact_id, draft.artifact_id, audit.artifact_id),
        )
