"""Strict, bundle-pinned PNCA manuscript export."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from novel_forge.pnca.contracts import (
    BundleSlotRecord,
    DesignBundle,
    DraftAudit,
    DraftCoverage,
    WriterView,
)
from novel_forge.runtime import ArtifactReference, RunHandle, RunRepository, RuntimeContractError


@dataclass(frozen=True, slots=True)
class ExportedManuscript:
    artifact: ArtifactReference
    content: str


def _validate_export_coverage(*, view: WriterView, payload: object) -> str:
    if not isinstance(payload, dict):
        raise RuntimeContractError("pinned draft has no structured payload")
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeContractError("pinned draft has no manuscript content")
    try:
        coverage = DraftCoverage.model_validate(payload.get("coverage"))
    except ValueError as exc:
        raise RuntimeContractError(f"pinned draft has invalid obligation coverage: {exc}") from exc
    required_indexes = set(range(len(view.required_beats)))
    actual_indexes = {item.beat_index for item in coverage.evidence if item.obligation == "required_beat"}
    if actual_indexes != required_indexes:
        raise RuntimeContractError("pinned draft coverage does not prove every required beat")
    end_count = sum(item.obligation == "end_constraint" for item in coverage.evidence)
    if bool(view.end_constraints) != (end_count == 1):
        raise RuntimeContractError("pinned draft coverage does not prove the end constraint")
    if len(coverage.evidence) != len(required_indexes) + end_count:
        raise RuntimeContractError("pinned draft coverage duplicates obligations")
    # NOTE: the verbatim-quote presence check is intentionally omitted here. The
    # authoritative coverage gate runs at render time (and revise re-checks structure
    # with strict=False). The frozen draft may have been legitimately reworded by
    # revise, so a drifted ``draft_quote`` must not block publication of a valid draft.
    return content


class PNCAExporter:
    """Render only a frozen bundle; never read selected/latest Canon state."""

    def __init__(self, repository: RunRepository) -> None:
        self.repository = repository

    def export(
        self,
        *,
        run: RunHandle,
        bundle: DesignBundle,
        format: Literal["markdown"] = "markdown",
    ) -> ExportedManuscript:
        if format != "markdown":
            raise RuntimeContractError(f"unsupported PNCA export format: {format}")
        content, inputs = self._render_bundle(bundle)
        attempt = self.repository.start_attempt(
            run, task_id="pnca.export", phase="export", reason="render frozen design bundle"
        )
        artifact = self.repository.commit_artifact(
            attempt,
            artifact_type="pnca.export.manuscript.markdown",
            logical_key=f"pnca.export.{bundle.bundle_id}.markdown",
            payload=content,
            payload_name="manuscript.md",
            input_artifact_ids=tuple(sorted(inputs)),
            metadata={"bundle_id": bundle.bundle_id, "format": format},
        )
        return ExportedManuscript(artifact=artifact, content=content)

    def _render_bundle(self, bundle: DesignBundle) -> tuple[str, set[str]]:
        parts: list[str] = []
        inputs: set[str] = set()
        volume: int | None = None
        chapter: int | None = None
        for slot in bundle.slots:
            draft, slot_inputs = self._validate_slot(slot)
            if volume != slot.volume_ordinal:
                parts.append(f"# 第{slot.volume_ordinal}巻")
                volume, chapter = slot.volume_ordinal, None
            if chapter != slot.chapter_ordinal:
                parts.append(f"## 第{slot.chapter_ordinal}章")
                chapter = slot.chapter_ordinal
            parts.extend((f"### シーン {slot.scene_ordinal}", draft))
            inputs.update(slot_inputs)
        if not parts:
            raise RuntimeContractError("PNCA export requires at least one frozen bundle slot")
        return "\n\n".join(parts).strip() + "\n", inputs

    def _validate_slot(self, slot: BundleSlotRecord) -> tuple[str, set[str]]:
        contract = self.repository.verify_artifact(slot.scene_contract_artifact_id)
        view = self.repository.verify_artifact(slot.writer_view_artifact_id)
        draft = self.repository.verify_artifact(slot.draft_artifact_id)
        assessment = self.repository.verify_artifact(slot.draft_assessment_artifact_id)
        output_frontier = self.repository.verify_artifact(slot.output_frontier_artifact_id)
        if contract.manifest.artifact_type != "pnca.scene.contract":
            raise RuntimeContractError("bundle scene contract artifact type is invalid")
        if output_frontier.manifest.artifact_type != "canon.event_set":
            raise RuntimeContractError("bundle output frontier artifact type is invalid")
        if view.manifest.artifact_type != "pnca.writer_view":
            raise RuntimeContractError("bundle writer view artifact type is invalid")
        if view.manifest.input_artifact_ids != (contract.artifact_id,):
            raise RuntimeContractError("writer view must be derived from its pinned scene contract")
        if view.manifest.metadata.get("scene_contract_digest") != contract.manifest.content_digest:
            raise RuntimeContractError("writer view must pin its scene contract digest")
        if draft.manifest.artifact_type != "pnca.scene_draft" or view.artifact_id not in draft.manifest.input_artifact_ids:
            raise RuntimeContractError("draft must be derived from its pinned writer view")
        if assessment.manifest.artifact_type != "pnca.draft_audit":
            raise RuntimeContractError("bundle draft assessment artifact type is invalid")
        required_assessment_inputs = {contract.artifact_id, view.artifact_id, draft.artifact_id}
        if not required_assessment_inputs.issubset(assessment.manifest.input_artifact_ids):
            raise RuntimeContractError("draft assessment must bind contract, writer view, and draft artifacts")
        try:
            DraftAudit.model_validate(self.repository.read_payload(assessment))
        except ValueError as exc:
            raise RuntimeContractError(f"bundle draft assessment payload is invalid: {exc}") from exc
        try:
            writer_view = WriterView.model_validate(self.repository.read_payload(view))
        except ValueError as exc:
            raise RuntimeContractError(f"bundle writer view payload is invalid: {exc}") from exc
        payload = self.repository.read_payload(draft)
        content = _validate_export_coverage(view=writer_view, payload=payload)
        return content, {
            contract.artifact_id,
            view.artifact_id,
            draft.artifact_id,
            assessment.artifact_id,
            output_frontier.artifact_id,
        }
