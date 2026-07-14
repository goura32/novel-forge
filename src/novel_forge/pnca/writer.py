"""PNCA prose rendering boundary."""

from __future__ import annotations

import logging

from dataclasses import dataclass

from novel_forge.pnca.contracts import DraftAudit, DraftCoverage, WriterView, WriterViewReview
from novel_forge.pnca.registry import PNCATaskExecutor
from novel_forge.pnca.validation import PNCAStructuralError, validate_writer_view
from novel_forge.runtime import ArtifactReference, RunHandle, RunRepository

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RenderedDraft:
    writer_view: ArtifactReference
    draft: ArtifactReference


def _validate_draft_coverage(*, view: WriterView, content: str, payload: object, strict: bool = True) -> DraftCoverage:
    """Accept proof for the WriterView's mandatory obligations.

    ``strict=True`` (render path): the authoritative publication gate. Every required
    beat and end constraint must be proven by a verbatim quote present in the draft.
    ``strict=False`` (revise path): the render path already proved coverage; revise only
    fixes audit issues and must not re-open the contract or abort on local-LLM rewording.
    We still verify the obligation *structure* (correct beats/end_constraint, no duplicates)
    but only warn when a quote drifts from the draft instead of raising.
    """
    # Local LLMs occasionally emit null/missing ``beat_index`` or ``draft_quote`` in
    # the coverage payload. Coerce null ``beat_index`` to its positional index (evidence
    # is emitted in obligation order) and null ``draft_quote`` to empty so validation can
    # run; the structure checks below still catch genuinely missing/duplicate obligations.
    if isinstance(payload, dict):
        evidence = payload.get("evidence")
        if isinstance(evidence, list):
            for idx, item in enumerate(evidence):
                if isinstance(item, dict):
                    if item.get("beat_index") is None:
                        item["beat_index"] = idx
                    if item.get("draft_quote") is None:
                        item["draft_quote"] = ""
    try:
        coverage = DraftCoverage.model_validate(payload)
    except ValueError as exc:
        raise PNCAStructuralError(f"PNCA render output requires valid obligation coverage: {exc}") from exc

    required_indexes = set(range(len(view.required_beats)))
    actual_indexes = {item.beat_index for item in coverage.evidence if item.obligation == "required_beat"}
    if actual_indexes != required_indexes:
        raise PNCAStructuralError("PNCA render coverage must prove every required_beat exactly once")
    end_count = sum(item.obligation == "end_constraint" for item in coverage.evidence)
    if bool(view.end_constraints) != (end_count == 1):
        raise PNCAStructuralError("PNCA render coverage must prove the end_constraint exactly once when present")
    if len(coverage.evidence) != len(required_indexes) + end_count:
        raise PNCAStructuralError("PNCA render coverage must not duplicate obligations")
    _punct = "　 \u3000。、，！？「」『』（）()：:；;\n\r\t"
    def _norm(text: str) -> str:
        return "".join(ch for ch in text if ch not in _punct)
    missing = [
        item for item in coverage.evidence
        if _norm(item.draft_quote) not in _norm(content)
    ]
    if missing:
        if strict:
            raise PNCAStructuralError("PNCA render coverage quotes must occur verbatim in the draft")
        _log.warning(
            "Revise coverage drift on %d quote(s); accepting revise (render gate already proved coverage)",
            len(missing),
        )
    return coverage


def _sentences(content: str) -> tuple[str, ...]:
    """Return non-empty Japanese sentence spans exactly as they occur in the draft."""
    spans: list[str] = []
    start = 0
    for index, char in enumerate(content):
        if char in "。！？":
            candidate = content[start:index + 1].strip()
            if candidate:
                spans.append(candidate)
            start = index + 1
    trailing = content[start:].strip()
    if trailing:
        spans.append(trailing)
    return tuple(spans)


def _coverage_from_selection(*, payload: object, content: str) -> object:
    """Turn model-selected sentence indices into exact immutable draft quotes."""
    if not isinstance(payload, dict) or not isinstance(payload.get("evidence"), list):
        return payload
    sentences = _sentences(content)
    evidence: list[object] = []
    for item in payload["evidence"]:
        if not isinstance(item, dict) or not isinstance(item.get("sentence_index"), int):
            evidence.append(item)
            continue
        sentence_index = item["sentence_index"]
        if not 0 <= sentence_index < len(sentences):
            evidence.append(item)
            continue
        evidence.append({key: value for key, value in item.items() if key != "sentence_index"} | {"draft_quote": sentences[sentence_index]})
    return {"evidence": evidence}


class PNCARenderer:
    """Persist a WriterView and its prose draft without a summary handoff."""

    def __init__(self, repository: RunRepository, *, max_writer_view_review_count: int = 3) -> None:
        self.repository = repository
        self.max_writer_view_review_count = max_writer_view_review_count

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
        view = self._review_writer_view(
            run=run,
            scene_contract_artifact_id=scene_contract_artifact_id,
            view=view,
            executor=executor,
            scope_id=scope_id,
        )
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
        render_result = executor.execute(
            task_id="pnca.scene.render",
            artifacts={"writer.view": view.model_dump(mode="json")},
            input_artifact_ids=(writer_view.artifact_id,),
            scope_id=scope_id,
        )
        content = render_result.get("content") if isinstance(render_result, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise PNCAStructuralError("PNCA render output requires non-empty content")
        coverage: DraftCoverage | None = None
        for coverage_cycle in range(5):
            coverage_result = executor.execute(
                task_id="pnca.scene.coverage",
                artifacts={
                    "writer.view": view.model_dump(mode="json"),
                    "scene.draft": {"content": content},
                },
                input_artifact_ids=(writer_view.artifact_id,),
                scope_id=f"{scope_id}.coverage.{coverage_cycle + 1}",
            )
            try:
                coverage = _validate_draft_coverage(
                    view=view, content=content,
                    payload=_coverage_from_selection(payload=coverage_result, content=content),
                )
                break
            except PNCAStructuralError as exc:
                rejected_attempt = self.repository.start_attempt(
                    run, task_id="pnca.scene.coverage.validation", phase="write", reason="reject invalid fixed-draft coverage"
                )
                self.repository.commit_artifact(
                    rejected_attempt, artifact_type="pnca.scene_coverage.rejected",
                    logical_key=f"pnca.scene_coverage.rejected.{scope_id}.{coverage_cycle + 1}",
                    payload={"content": content, "result": coverage_result, "error": str(exc)},
                    payload_name="rejected_coverage.json", input_artifact_ids=(writer_view.artifact_id,),
                )
                if coverage_cycle == 4:
                    raise
                # Regenerate the draft so coverage can quote it verbatim on the next pass.
                render_result = executor.execute(
                    task_id="pnca.scene.render",
                    artifacts={"writer.view": view.model_dump(mode="json")},
                    input_artifact_ids=(writer_view.artifact_id,),
                    scope_id=f"{scope_id}.render.{coverage_cycle + 2}",
                )
                content = render_result.get("content") if isinstance(render_result, dict) else None
                if not isinstance(content, str) or not content.strip():
                    raise PNCAStructuralError("PNCA render output requires non-empty content") from None
        assert coverage is not None
        draft_attempt = self.repository.start_attempt(
            run, task_id="pnca.scene.render", phase="write", reason="render scene draft"
        )
        draft = self.repository.commit_artifact(
            draft_attempt,
            artifact_type="pnca.scene_draft",
            logical_key=f"pnca.scene_draft.{scope_id}",
            payload={"content": content, "coverage": coverage.model_dump(mode="json")},
            payload_name="draft.json",
            input_artifact_ids=(writer_view.artifact_id,),
        )
        return RenderedDraft(writer_view=writer_view, draft=draft)

    def _review_writer_view(
        self,
        *,
        run: RunHandle,
        scene_contract_artifact_id: str,
        view: WriterView,
        executor: PNCATaskExecutor,
        scope_id: str,
    ) -> WriterView:
        """Persist editorial WriterView feedback without letting it create a rewrite loop."""
        review_attempt = self.repository.start_attempt(
            run,
            task_id="pnca.writer_view.review",
            phase="write",
            reason="review writer view before prose render",
        )
        review = WriterViewReview.model_validate(
            executor.execute(
                task_id="pnca.writer_view.review",
                artifacts={"writer.view": view.model_dump(mode="json")},
                input_artifact_ids=(scene_contract_artifact_id,),
                scope_id=f"{scope_id}.writer-view.review.1",
            )
        )
        self.repository.commit_artifact(
            review_attempt,
            artifact_type="pnca.writer_view.review",
            logical_key=f"pnca.writer_view.review.{scope_id}.1",
            payload=review.model_dump(mode="json"),
            payload_name="review.json",
            input_artifact_ids=(scene_contract_artifact_id,),
        )
        return view

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
        # Revise must NOT re-open the coverage contract (render is authoritative). The
        # revise LLM frequently mis-reports ``beat_index``/coverage structure, so we
        # inherit the render-validated coverage from the original draft instead of
        # trusting the revise output's self-reported coverage.
        original_payload = self.repository.read_payload(draft)
        original_coverage = original_payload.get("coverage") if isinstance(original_payload, dict) else None
        if original_coverage:
            try:
                coverage = DraftCoverage.model_validate(original_coverage)
            except ValueError:
                coverage = _validate_draft_coverage(
                    view=writer_view, content=content,
                    payload=result.get("coverage") if isinstance(result, dict) else None,
                    strict=False,
                )
        else:
            coverage = _validate_draft_coverage(
                view=writer_view, content=content,
                payload=result.get("coverage") if isinstance(result, dict) else None,
                strict=False,
            )
        attempt = self.repository.start_attempt(run, task_id="pnca.scene.revise", phase="write", reason="resolve draft audit issues")
        return self.repository.commit_artifact(
            attempt, artifact_type="pnca.scene_draft", logical_key=f"pnca.scene_draft.revised.{scope_id}",
            payload={"content": content, "coverage": coverage.model_dump(mode="json")}, payload_name="draft.json",
            input_artifact_ids=(writer_view_artifact_id, draft.artifact_id, audit.artifact_id),
        )
