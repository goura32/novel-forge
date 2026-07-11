"""Snapshot-authoritative public workflow.

This is the only production path for plan/design/write/export.  It deliberately
has no dependency on legacy state files, fixed output paths, or live Canon
stores: every input is read from the run's immutable selection snapshot and
all outputs are published by appending a descendant snapshot.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from novel_forge.runtime import (
    ArtifactReference,
    AttemptHandle,
    RunHandle,
    RunRepository,
    RuntimeContractError,
    SelectionSnapshot,
)

TaskRunner = Callable[[str, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    selection_snapshot_id: str


class RuntimeWorkflow:
    """Execute a run using only verified artifacts selected by snapshots."""

    def __init__(
        self,
        repository: RunRepository,
        run: RunHandle,
        *,
        slug: str | None = None,
        task_runner: TaskRunner,
        max_review_count: int = 3,
        max_summary_review_count: int = 2,
    ) -> None:
        self.repository = repository
        self.run = run
        self.slug = slug
        self.task_runner = task_runner
        self.max_review_count = max_review_count
        self.max_summary_review_count = max_summary_review_count
        self._snapshot: SelectionSnapshot | None = None
        if run.manifest.input_snapshot_id is not None:
            if not slug:
                raise RuntimeContractError("a non-bootstrap workflow requires a series slug")
            self._snapshot = repository.load_snapshot(slug, run.manifest.input_snapshot_id)

    @property
    def snapshot(self) -> SelectionSnapshot:
        if self._snapshot is None:
            raise RuntimeContractError("bootstrap run has no input selection snapshot")
        return self._snapshot

    def _selected(self, slot: str) -> ArtifactReference:
        try:
            artifact_id = self.snapshot.slots[slot]
        except KeyError as exc:
            raise RuntimeContractError(f"input snapshot is missing required slot: {slot}") from exc
        return self.repository.verify_artifact(artifact_id)

    def _payload(self, slot: str) -> dict[str, Any]:
        payload = self.repository.read_payload(self._selected(slot))
        if not isinstance(payload, dict):
            raise RuntimeContractError(f"artifact payload must be an object: {slot}")
        return payload

    def _attempt(self, task_id: str, reason: str) -> AttemptHandle:
        phase = task_id.split(".", 1)[0]
        return self.repository.start_attempt(self.run, task_id=task_id, phase=phase, reason=reason)

    def _artifact(
        self,
        *,
        task_id: str,
        reason: str,
        artifact_type: str,
        logical_key: str,
        payload: dict[str, Any],
        payload_name: str,
        metadata: dict[str, Any] | None = None,
        input_artifact_ids: tuple[str, ...] = (),
        quality_status: str | None = None,
    ) -> ArtifactReference:
        attempt = self._attempt(task_id, reason)
        return self.repository.commit_artifact(
            attempt,
            artifact_type=artifact_type,
            logical_key=logical_key,
            payload=payload,
            payload_name=payload_name,
            metadata=metadata,
            input_artifact_ids=input_artifact_ids,
            quality_status=quality_status,  # type: ignore[arg-type]
        )

    def _run_task(
        self,
        task_id: str,
        values: dict[str, Any],
        *,
        reason: str,
    ) -> tuple[AttemptHandle, dict[str, Any]]:
        attempt = self._attempt(task_id, reason)
        try:
            result = self.task_runner(task_id, values)
        except Exception as exc:
            self.repository.fail_attempt(
                attempt,
                error_code="TASK_ERROR",
                retryable=False,
                detail=str(exc),
            )
            raise
        if not isinstance(result, dict):
            self.repository.fail_attempt(
                attempt,
                error_code="INVALID_TASK_RESULT",
                retryable=False,
                detail=repr(result),
            )
            raise RuntimeContractError(f"task runner returned non-object for {task_id}")
        return attempt, result

    def _commit_task_result(
        self,
        attempt: AttemptHandle,
        *,
        artifact_type: str,
        logical_key: str,
        payload: dict[str, Any],
        payload_name: str,
        metadata: dict[str, Any] | None = None,
        input_artifact_ids: tuple[str, ...] = (),
        quality_status: str | None = None,
    ) -> ArtifactReference:
        return self.repository.commit_artifact(
            attempt,
            artifact_type=artifact_type,
            logical_key=logical_key,
            payload=payload,
            payload_name=payload_name,
            metadata=metadata,
            input_artifact_ids=input_artifact_ids,
            quality_status=quality_status,  # type: ignore[arg-type]
        )

    def _publish(self, updates: dict[str, str], reason: str) -> SelectionSnapshot:
        if not self.slug:
            raise RuntimeContractError("cannot publish a selection snapshot without a series slug")
        slots = dict(self._snapshot.slots) if self._snapshot is not None else {}
        slots.update(updates)
        snapshot = self.repository.create_selection_snapshot(
            slug=self.slug,
            slots=slots,
            base_snapshot_id=self._snapshot.selection_snapshot_id if self._snapshot else None,
            reason=reason,
        )
        self._snapshot = snapshot
        return snapshot

    def bootstrap_plan(
        self,
        *,
        slug: str,
        plan: dict[str, Any],
        canon_seed: dict[str, Any],
    ) -> SelectionSnapshot:
        """Commit plan + immutable Canon roots, then atomically establish snapshot 1."""
        if self.run.manifest.input_snapshot_id is not None:
            raise RuntimeContractError("bootstrap_plan requires a bootstrap run")
        self.slug = slug
        plan_ref = self._artifact(
            task_id="plan.series.generate",
            reason="assemble selected plan",
            artifact_type="plan.series",
            logical_key="plan.series",
            payload=plan,
            payload_name="plan-series.json",
        )
        seed_ref = self._artifact(
            task_id="plan.canon_seed.generate",
            reason="create Canon seed",
            artifact_type="canon.seed",
            logical_key="canon.seed",
            payload=canon_seed,
            payload_name="canon-seed.json",
        )
        frontier_ref = self._artifact(
            task_id="plan.canon_frontier.generate",
            reason="create empty Canon frontier",
            artifact_type="canon.event_set",
            logical_key="canon.frontier",
            payload={"events": []},
            payload_name="canon-frontier.json",
            metadata={"root": True},
        )
        # Root frontier consumes no earlier Canon, but its lineage is fixed to seed.
        frontier_manifest = frontier_ref.manifest.model_copy(
            update={"canon_lineage_root_digest": seed_ref.manifest.content_digest}
        )
        # The manifest is immutable, therefore the reference above cannot be edited.
        # Commit a correct root with its own attempt and use it instead.
        if frontier_manifest.canon_lineage_root_digest != frontier_ref.manifest.canon_lineage_root_digest:
            attempt = self._attempt("plan.canon_frontier.generate", "bind Canon lineage root")
            frontier_ref = self.repository.commit_artifact(
                attempt,
                artifact_type="canon.event_set",
                logical_key="canon.frontier",
                payload={"events": []},
                payload_name="canon-frontier-root.json",
                canon_lineage_root_digest=seed_ref.manifest.content_digest,
            )
        return self._publish(
            {
                "plan.series": plan_ref.artifact_id,
                "canon.seed": seed_ref.artifact_id,
                "canon.frontier": frontier_ref.artifact_id,
            },
            "bootstrap plan accepted",
        )

    def publish_design(self, volume: int, design: dict[str, Any]) -> SelectionSnapshot:
        self._payload("plan.series")
        slot = f"design.vol{volume:02d}"
        ref = self._artifact(
            task_id="design.volume.generate",
            reason="accept volume design",
            artifact_type="design.volume",
            logical_key=slot,
            payload=design,
            payload_name=f"{slot}.json",
            input_artifact_ids=(self._selected("plan.series").artifact_id,),
        )
        return self._publish({slot: ref.artifact_id}, f"design volume {volume} accepted")

    def write_volume(self, volume: int) -> WorkflowResult:
        design_slot = f"design.vol{volume:02d}"
        design_ref = self._selected(design_slot)
        design = self._payload(design_slot)
        scenes = design.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            raise RuntimeContractError(f"selected design has no scenes: {design_slot}")
        previous_summary: dict[str, Any] | None = None
        for raw_scene in scenes:
            if not isinstance(raw_scene, dict):
                raise RuntimeContractError("design scene must be an object")
            chapter = int(raw_scene["chapter_number"])
            scene = int(raw_scene["scene_number"])
            stem = f"write.vol{volume:02d}.ch{chapter:02d}.sc{scene:02d}"
            draft_attempt, draft = self._run_task(
                "write.draft.generate",
                {"scene_design": raw_scene, "previous_summary": previous_summary},
                reason="draft generation",
            )
            draft_ref = self._commit_task_result(
                draft_attempt,
                artifact_type="write.draft",
                logical_key=f"{stem}.draft",
                payload=draft,
                payload_name=f"{stem}.draft.json",
                input_artifact_ids=(design_ref.artifact_id,),
            )
            final_draft = draft_ref
            final_review: ArtifactReference | None = None
            review: dict[str, Any] = {"issues": []}
            for cycle in range(self.max_review_count):
                review_attempt, review = self._run_task(
                    "write.draft.review",
                    {"scene_design": raw_scene, "draft": self.repository.read_payload(final_draft)},
                    reason=f"draft review {cycle + 1}",
                )
                issues = review.get("issues", [])
                review_key = f"{stem}.final_review" if not issues or cycle + 1 == self.max_review_count else f"{stem}.draft_review.{cycle + 1}"
                final_review = self._commit_task_result(
                    review_attempt,
                    artifact_type="review.issues",
                    logical_key=review_key,
                    payload=review,
                    payload_name=f"{review_key}.json",
                    input_artifact_ids=(final_draft.artifact_id,),
                )
                if not issues or cycle + 1 == self.max_review_count:
                    break
                revise_attempt, revised = self._run_task(
                    "write.draft.revise",
                    {"scene_design": raw_scene, "draft": self.repository.read_payload(final_draft), "review": review},
                    reason=f"draft revise {cycle + 1}",
                )
                final_draft = self._commit_task_result(
                    revise_attempt,
                    artifact_type="write.draft",
                    logical_key=f"{stem}.draft_candidate.{cycle + 1}",
                    payload=revised,
                    payload_name=f"{stem}.draft_candidate.{cycle + 1}.json",
                    input_artifact_ids=(final_draft.artifact_id, final_review.artifact_id),
                )
                # Selected slot must name the final draft even if it came from revise.
                if cycle + 1 == self.max_review_count:
                    break
            if final_review is None:
                raise RuntimeContractError("draft review was not recorded")
            # Ensure the selected final draft has the canonical slot key.
            if final_draft.manifest.logical_key != f"{stem}.draft":
                selected_attempt = self._attempt("write.draft.revise", "commit final selected draft")
                final_draft = self.repository.commit_artifact(
                    selected_attempt,
                    artifact_type="write.draft",
                    logical_key=f"{stem}.draft",
                    payload=self.repository.read_payload(final_draft),
                    payload_name=f"{stem}.draft.final.json",
                    input_artifact_ids=(final_draft.artifact_id,),
                    quality_status="review_limit_reached" if review.get("issues") else "passed",
                )
            summary_ref, summary_review = self._make_summary(
                raw_scene, final_draft, previous_summary, stem
            )
            snapshot = self._publish(
                {
                    f"{stem}.draft": final_draft.artifact_id,
                    f"{stem}.final_review": final_review.artifact_id,
                    f"{stem}.summary": summary_ref.artifact_id,
                },
                f"write scene {volume}/{chapter}/{scene} accepted",
            )
            previous_summary = self.repository.read_payload(summary_ref)
        return WorkflowResult(snapshot.selection_snapshot_id)

    def _make_summary(
        self,
        scene: dict[str, Any],
        draft_ref: ArtifactReference,
        previous_summary: dict[str, Any] | None,
        stem: str,
    ) -> tuple[ArtifactReference, ArtifactReference]:
        draft = self.repository.read_payload(draft_ref)
        generate_attempt, candidate = self._run_task(
            "write.summary.generate",
            {"scene_design": scene, "draft": draft, "previous_summary": previous_summary},
            reason="summary generation",
        )
        candidate_ref = self._commit_task_result(
            generate_attempt,
            artifact_type="write.summary",
            logical_key=f"{stem}.summary_candidate.1",
            payload=candidate,
            payload_name=f"{stem}.summary_candidate.1.json",
            input_artifact_ids=(draft_ref.artifact_id,),
        )
        final = candidate_ref
        final_review: ArtifactReference | None = None
        review: dict[str, Any] = {"issues": []}
        for cycle in range(self.max_summary_review_count):
            review_attempt, review = self._run_task(
                "write.summary.review",
                {"draft": draft, "summary": self.repository.read_payload(final)},
                reason=f"summary review {cycle + 1}",
            )
            final_review = self._commit_task_result(
                review_attempt,
                artifact_type="review.issues",
                logical_key=f"{stem}.summary_review.{cycle + 1}",
                payload=review,
                payload_name=f"{stem}.summary_review.{cycle + 1}.json",
                input_artifact_ids=(draft_ref.artifact_id, final.artifact_id),
            )
            if not review.get("issues") or cycle + 1 == self.max_summary_review_count:
                break
            revise_attempt, revised = self._run_task(
                "write.summary.revise",
                {"draft": draft, "summary": self.repository.read_payload(final), "review": review},
                reason=f"summary revise {cycle + 1}",
            )
            final = self._commit_task_result(
                revise_attempt,
                artifact_type="write.summary",
                logical_key=f"{stem}.summary_candidate.{cycle + 2}",
                payload=revised,
                payload_name=f"{stem}.summary_candidate.{cycle + 2}.json",
                input_artifact_ids=(draft_ref.artifact_id, final_review.artifact_id),
            )
        if final_review is None:
            raise RuntimeContractError("summary review was not recorded")
        status: Literal["passed", "review_limit_reached"] = (
            "review_limit_reached" if review.get("issues") else "passed"
        )
        selected_attempt = self._attempt("write.summary.revise", "commit selected summary")
        selected = self.repository.commit_artifact(
            selected_attempt,
            artifact_type="write.summary",
            logical_key=f"{stem}.summary",
            payload=self.repository.read_payload(final),
            payload_name=f"{stem}.summary.final.json",
            input_artifact_ids=(draft_ref.artifact_id, final.artifact_id, final_review.artifact_id),
            quality_status=status,
            metadata={
                "source_draft_artifact_id": draft_ref.artifact_id,
                "summary_review_artifact_id": final_review.artifact_id,
                "summary_quality_status": status,
            },
        )
        return selected, final_review

    def export_volume(self, volume: int) -> dict[str, Any]:
        design = self._payload(f"design.vol{volume:02d}")
        scenes = design.get("scenes")
        if not isinstance(scenes, list):
            raise RuntimeContractError("selected design has no scenes")
        contents: list[str] = []
        input_ids: list[str] = []
        for raw_scene in scenes:
            chapter = int(raw_scene["chapter_number"])
            scene = int(raw_scene["scene_number"])
            stem = f"write.vol{volume:02d}.ch{chapter:02d}.sc{scene:02d}"
            draft_ref = self._selected(f"{stem}.draft")
            self._selected(f"{stem}.summary")
            self._selected(f"{stem}.final_review")
            draft = self.repository.read_payload(draft_ref)
            contents.append(str(draft.get("content", "")))
            input_ids.append(draft_ref.artifact_id)
        manuscript = {"content": "\n\n---\n\n".join(contents), "volume": volume}
        ref = self._artifact(
            task_id="write.export.generate",
            reason="assemble pinned manuscript",
            artifact_type="export.manuscript",
            logical_key=f"export.vol{volume:02d}.manuscript",
            payload=manuscript,
            payload_name=f"export.vol{volume:02d}.manuscript.json",
            input_artifact_ids=tuple(input_ids),
            metadata={"input_snapshot_id": self.snapshot.selection_snapshot_id},
        )
        return {**manuscript, "artifact_id": ref.artifact_id, "input_snapshot_id": self.snapshot.selection_snapshot_id}
