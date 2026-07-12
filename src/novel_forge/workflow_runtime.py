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

from pydantic import ValidationError

from novel_forge.canon.design import CastCharacter, SceneDesign
from novel_forge.canon.frontier import (
    FrontierPayloadError,
    SeedPayloadError,
    replay_frontier,
    validate_frontier_payload,
)
from novel_forge.canon.models import Canon, ContextScope, EntityRef, SceneLocation, WriterContext
from novel_forge.canon.runtime import (
    apply_reviewed_patch,
    attach_projection,
    review_scene_patch,
)
from novel_forge.llm_client import LLMError, LLMTransportError
from novel_forge.prompts import PromptManager
from novel_forge.review_contracts import validate_draft_review_actionability
from novel_forge.runtime import (
    ArtifactReference,
    AttemptCapture,
    AttemptHandle,
    RunHandle,
    RunRepository,
    RuntimeContractError,
    SelectionSnapshot,
    digest_json,
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
        max_retry_count: int = 7,
    ) -> None:
        self.repository = repository
        self.run = run
        self.slug = slug
        self.task_runner = task_runner
        self.max_review_count = max_review_count
        self.max_summary_review_count = max_summary_review_count
        self.max_retry_count = max_retry_count
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

    def load_canon(self) -> Canon:
        """Replay the Canon selected by this workflow's immutable snapshot.

        ``canon.seed`` and ``canon.frontier`` are both verified artifacts.  No
        mutable Canon store or fixed project file participates in this read.
        """
        try:
            return replay_frontier(
                self._payload("canon.seed"),
                self._payload("canon.frontier"),
            )
        except (SeedPayloadError, FrontierPayloadError) as exc:
            raise RuntimeContractError(f"selected Canon artifacts are invalid: {exc}") from exc

    def publish_canon_event(self, event_payload: dict[str, Any]) -> SelectionSnapshot:
        """Replace one active scene event and publish a descendant frontier.

        The selected frontier is the full active event set.  Revisions replace
        only their source scene and are replayed before persistence; a failed
        replay cannot advance the selection snapshot.
        """
        try:
            incoming = validate_frontier_payload({"events": [event_payload]})[0]
            active = {
                event.source.scene_id: event
                for event in validate_frontier_payload(self._payload("canon.frontier"))
            }
        except FrontierPayloadError as exc:
            raise RuntimeContractError(f"Canon event payload is invalid: {exc}") from exc

        previous = active.get(incoming.source.scene_id)
        if previous is not None and incoming.source.revision <= previous.source.revision:
            if incoming.model_dump(mode="json") == previous.model_dump(mode="json"):
                return self.snapshot
            raise RuntimeContractError(
                "Canon event revision must exceed the selected event for its scene"
            )
        active[incoming.source.scene_id] = incoming
        frontier_payload = {"events": [event.model_dump(mode="json") for event in active.values()]}
        try:
            replay_frontier(self._payload("canon.seed"), frontier_payload)
        except (SeedPayloadError, FrontierPayloadError, ValueError) as exc:
            raise RuntimeContractError(
                f"candidate Canon frontier cannot be replayed: {exc}"
            ) from exc

        parent = self._selected("canon.frontier")
        seed = self._selected("canon.seed")
        patch_key = f"canon.patch.{incoming.source.scene_id}.r{incoming.source.revision}"
        patch_ref = self._artifact(
            task_id="canon.patch.review",
            reason="record reviewed Canon patch evidence",
            artifact_type="canon.patch",
            logical_key=patch_key,
            payload=event_payload,
            payload_name=f"{patch_key}.json",
            input_artifact_ids=(parent.artifact_id, seed.artifact_id),
            quality_status="passed",
        )
        logical_key = f"canon.frontier.{incoming.source.scene_id}.r{incoming.source.revision}"
        attempt = self._attempt("canon.event.apply", "accept reviewed Canon event")
        ref = self.repository.commit_artifact(
            attempt,
            artifact_type="canon.event_set",
            logical_key=logical_key,
            payload=frontier_payload,
            payload_name=f"{logical_key}.json",
            input_artifact_ids=(parent.artifact_id, seed.artifact_id),
            canon_lineage_root_digest=seed.manifest.content_digest,
            input_canon_frontier_digest=parent.manifest.content_digest,
            parent_frontier_artifact_id=parent.artifact_id,
            parent_frontier_digest=parent.manifest.content_digest,
            source_patch_artifact_ids=(patch_ref.artifact_id,),
            metadata={
                "replaced_scene_id": incoming.source.scene_id,
                "revision": incoming.source.revision,
                "event_id": incoming.event_id,
            },
        )
        return self._publish({"canon.frontier": ref.artifact_id}, "Canon event accepted")

    def accept_scene_design(
        self,
        design: SceneDesign,
        patch: dict[str, Any],
    ) -> tuple[SelectionSnapshot, SceneDesign]:
        """Accept one typed scene only through the v2 Canon event boundary.

        The selected snapshot supplies the only Canon input.  This method
        projects writer context, performs deterministic Canon patch review,
        mints an approved event, advances ``canon.frontier``, then persists the
        applied typed SceneDesign.  It intentionally does not touch a fixed
        ``CanonEventStore`` or legacy design file.
        """
        if design.status != "draft" or design.canon_patch is not None:
            raise RuntimeContractError(
                "public scene acceptance requires a draft SceneDesign without canon_patch"
            )
        canon = self.load_canon()
        try:
            active_events = list(validate_frontier_payload(self._payload("canon.frontier")))
            projected = attach_projection(design, canon)
            review = review_scene_patch(projected, patch, canon)
        except (FrontierPayloadError, ValueError) as exc:
            raise RuntimeContractError(f"scene design review failed: {exc}") from exc
        if not review.passed:
            raise RuntimeContractError(f"scene design review rejected: {review.issues}")

        prior = next(
            (event for event in active_events if event.source.scene_id == projected.scene_id),
            None,
        )
        revision = 1 if prior is None else prior.source.revision + 1
        try:
            _updated_canon, event = apply_reviewed_patch(
                projected,
                patch,
                canon,
                None,
                review,
                revision=revision,
                active_events=active_events,
            )
        except ValueError as exc:
            raise RuntimeContractError(f"reviewed scene patch could not be applied: {exc}") from exc

        self.publish_canon_event(event.model_dump(mode="json"))
        frontier_ref = self._selected("canon.frontier")
        scene_key = f"design.scene.{projected.scene_id}"
        scene_ref = self._artifact(
            task_id="design.scene.accept",
            reason="persist applied typed scene design",
            artifact_type="design.scene",
            logical_key=scene_key,
            payload=projected.model_dump(mode="json"),
            payload_name=f"{scene_key}.json",
            input_artifact_ids=(frontier_ref.artifact_id,),
            quality_status="passed",
        )
        snapshot = self._publish(
            {scene_key: scene_ref.artifact_id},
            f"scene {projected.scene_id} accepted through Canon frontier",
        )
        return snapshot, projected

    def _attempt(self, task_id: str, reason: str, *, retry_number: int = 1) -> AttemptHandle:
        phase = task_id.split(".", 1)[0]
        return self.repository.start_attempt(
            self.run,
            task_id=task_id,
            phase=phase,
            reason=reason,
            retry_number=retry_number,
        )

    def _artifact(
        self,
        *,
        task_id: str,
        reason: str,
        artifact_type: str,
        logical_key: str,
        payload: Any,
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
        """Run a task; schema/contract retry attempts get a fresh Ollama seed."""
        last_error: Exception | None = None
        for retry_number in range(1, self.max_retry_count + 1):
            attempt = self._attempt(task_id, reason, retry_number=retry_number)
            set_retry_seed = getattr(self.task_runner, "set_retry_seed", None)
            if retry_number > 1 and callable(set_retry_seed):
                set_retry_seed(retry_number)
            set_capture = getattr(self.task_runner, "set_attempt_capture", None)
            if callable(set_capture):
                set_capture(AttemptCapture(self.repository, attempt, self.run.manifest.verbose))
            try:
                result = self.task_runner(task_id, values)
            except LLMTransportError as exc:
                self.repository.fail_attempt(
                    attempt,
                    error_code="TRANSPORT_ERROR",
                    retryable=False,
                    detail=str(exc),
                )
                raise
            except LLMError as exc:
                retryable = retry_number < self.max_retry_count
                self.repository.fail_attempt(
                    attempt,
                    error_code="CONTRACT_ERROR",
                    retryable=retryable,
                    detail=str(exc),
                )
                last_error = exc
                if retryable:
                    continue
                raise
            except Exception as exc:
                self.repository.fail_attempt(
                    attempt,
                    error_code="TASK_ERROR",
                    retryable=False,
                    detail=str(exc),
                )
                raise
            finally:
                if callable(set_capture):
                    set_capture(None)
            if not isinstance(result, dict):
                detail = repr(result)
                error = RuntimeContractError(f"task runner returned non-object for {task_id}")
                retryable = retry_number < self.max_retry_count
                self.repository.fail_attempt(
                    attempt,
                    error_code="INVALID_TASK_RESULT",
                    retryable=retryable,
                    detail=detail,
                )
                last_error = error
                if retryable:
                    continue
                raise error
            if task_id == "write.draft.review":
                semantic_errors = validate_draft_review_actionability(values["draft"], result)
                if semantic_errors:
                    error = LLMError("draft review semantic contract: " + "; ".join(semantic_errors))
                    retryable = retry_number < self.max_retry_count
                    self.repository.fail_attempt(
                        attempt,
                        error_code="CONTRACT_ERROR",
                        retryable=retryable,
                        detail=str(error),
                    )
                    last_error = error
                    if retryable:
                        continue
                    raise error
            return attempt, result
        assert last_error is not None
        raise last_error

    def _review_and_revise(
        self,
        stem: str,
        candidate: dict[str, Any],
        candidate_attempt: AttemptHandle,
        *,
        review_values: Callable[[dict[str, Any]], dict[str, Any]],
        revise_values: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
        contract_issues: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None,
    ) -> tuple[AttemptHandle, dict[str, Any]]:
        """Run bounded cross-phase review/revision; the final revision advances downstream."""
        attempt, current = candidate_attempt, candidate
        for cycle in range(1, self.max_review_count + 1):
            _, llm_review = self._run_task(
                f"{stem}.review", review_values(current), reason=f"review {stem} candidate"
            )
            issues = list(llm_review.get("issues", []))
            if contract_issues is not None:
                issues.extend(contract_issues(current))
            if not issues:
                return attempt, current
            review = {"issues": issues}
            if cycle == self.max_review_count:
                return attempt, current
            attempt, current = self._run_task(
                f"{stem}.revise",
                revise_values(current, review),
                reason=f"revise {stem} after review",
            )
        raise AssertionError("unreachable review loop")

    def _commit_task_result(
        self,
        attempt: AttemptHandle,
        *,
        task_id: str,
        artifact_type: str,
        logical_key: str,
        payload: dict[str, Any],
        payload_name: str,
        metadata: dict[str, Any] | None = None,
        input_artifact_ids: tuple[str, ...] = (),
        quality_status: str | None = None,
    ) -> ArtifactReference:
        from novel_forge.task_registry import DEFAULT_TASK_REGISTRY

        prompt = PromptManager().render_task(task_id, {})
        schema = DEFAULT_TASK_REGISTRY.load_schema(task_id)
        prompt_digest = digest_json(prompt)
        schema_digest = digest_json(schema)
        return self.repository.commit_artifact(
            attempt,
            artifact_type=artifact_type,
            logical_key=logical_key,
            payload=payload,
            payload_name=payload_name,
            metadata=metadata,
            input_artifact_ids=input_artifact_ids,
            quality_status=quality_status,  # type: ignore[arg-type]
            prompt_digest=prompt_digest,
            schema_digest=schema_digest,
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
        plan_attempt: AttemptHandle | None = None,
    ) -> SelectionSnapshot:
        """Commit plan + immutable Canon roots, then atomically establish snapshot 1."""
        if self.run.manifest.input_snapshot_id is not None:
            raise RuntimeContractError("bootstrap_plan requires a bootstrap run")
        self.slug = slug
        plan_ref = (
            self._commit_task_result(
                plan_attempt,
                task_id="plan.series.generate",
                artifact_type="plan.series",
                logical_key="plan.series",
                payload=plan,
                payload_name="plan-series.json",
            )
            if plan_attempt is not None
            else self._artifact(
                task_id="plan.series.generate",
                reason="assemble selected plan",
                artifact_type="plan.series",
                logical_key="plan.series",
                payload=plan,
                payload_name="plan-series.json",
            )
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
        if (
            frontier_manifest.canon_lineage_root_digest
            != frontier_ref.manifest.canon_lineage_root_digest
        ):
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

    @staticmethod
    def _writer_handoff(summary: dict[str, Any] | None) -> dict[str, Any] | None:
        """Expose only the six §summary fields safe for the next draft prompt."""
        if summary is None:
            return None
        handoff: dict[str, Any] = {
            key: summary.get(key)
            for key in (
                "summary",
                "end_state",
                "character_changes",
                "world_or_item_changes",
                "unresolved_threads",
                "next_scene_handoff",
            )
            if key in summary
        }
        for key in ("character_changes", "world_or_item_changes", "unresolved_threads"):
            value = handoff.get(key)
            if isinstance(value, list):
                handoff[key] = [
                    {field: item[field] for field in item if field != "evidence"}
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
        return handoff

    @staticmethod
    def _design_author_context(canon: Canon) -> dict[str, Any]:
        """Return the author context and the exact Canon IDs permitted to design.

        IDs are intentionally supplied to the design/review/revise prompts.  An
        LLM must select one of these opaque IDs; names are narrative labels only
        and are never resolved by fuzzy matching at the runtime boundary.
        """
        names = {character.id: character.identity.display_name for character in canon.characters}
        collective_names = {collective.id: collective.name for collective in canon.collectives}
        return {
            "series_constraints": [constraint.statement for constraint in canon.series.constraints],
            "world_rules": [rule.statement for rule in canon.world_rules],
            "characters": [
                {
                    "id": character.id,
                    "display_name": character.identity.display_name,
                    "current_state": character.continuity_card.current_state,
                    "affiliations": [
                        collective_names.get(affiliation.collective.id, "")
                        for affiliation in character.affiliations
                    ],
                }
                for character in canon.characters
            ],
            "locations": [
                {
                    "id": location.id,
                    "name": location.name,
                    "immutable_constraints": location.immutable_constraints,
                    "current_state": location.current_state,
                }
                for location in canon.locations
            ],
            "relationships": [
                {
                    "participants": [
                        names.get(participant_id, "")
                        for participant_id in relationship.participant_ids
                    ],
                    "shared_state": relationship.shared_state,
                    "arc_summary": relationship.arc_summary,
                }
                for relationship in canon.relationships
                if relationship.lifecycle == "active"
            ],
            "active_subplots": [
                {
                    "name": subplot.name,
                    "current_state": subplot.current_state,
                    "stakes": subplot.stakes,
                }
                for subplot in canon.subplots
                if subplot.status == "active"
            ],
            "unresolved_foreshadowing": [
                {"description": item.description, "intended_payoff": item.intended_payoff}
                for item in canon.foreshadowing
                if item.status == "planted"
            ],
            "active_deadlines": [
                {"statement": deadline.statement, "due": deadline.due_marker.label}
                for deadline in (canon.chronology.active_deadlines if canon.chronology else [])
            ],
        }

    @staticmethod
    def _require_canon_id(
        canon: Canon, entity_kind: Literal["character", "location"], value: object
    ) -> str:
        if not isinstance(value, str) or not value:
            raise RuntimeContractError(f"scene {entity_kind}_id must be a non-empty Canon ID")
        entities = canon.characters if entity_kind == "character" else canon.locations
        if any(entity.id == value for entity in entities):
            return value
        raise RuntimeContractError(f"scene {entity_kind}_id does not exist in Canon: {value!r}")

    @staticmethod
    def _compile_scene_updates(canon: Canon, updates: object) -> dict[str, Any]:
        """Compile the small, ID-only scene DSL to the strict CanonPatch shape."""
        if not isinstance(updates, list):
            raise RuntimeContractError("scene canon_updates must be an array")
        character_ids = {entity.id for entity in canon.characters}
        location_ids = {entity.id for entity in canon.locations}
        artifact_ids = {entity.id for entity in canon.artifacts}
        patch: dict[str, Any] = {
            "characters": {"state_updates": []},
            "locations": {"state_updates": []},
            "artifacts": {"custody_updates": [], "condition_updates": []},
        }
        for index, update in enumerate(updates):
            if not isinstance(update, dict):
                raise RuntimeContractError(f"canon_updates[{index}] must be an object")
            operation, target_id, value = (
                update.get("operation"),
                update.get("target_id"),
                update.get("value"),
            )
            if not isinstance(value, str) or not value.strip():
                raise RuntimeContractError(f"canon_updates[{index}].value must be non-empty")
            if operation == "set_character_state":
                if target_id not in character_ids:
                    raise RuntimeContractError(
                        f"canon_updates[{index}].target_id is not a Canon character: {target_id!r}"
                    )
                patch["characters"]["state_updates"].append(
                    {"character": {"kind": "character", "id": target_id}, "current_state": value}
                )
            elif operation == "set_location_state":
                if target_id not in location_ids:
                    raise RuntimeContractError(
                        f"canon_updates[{index}].target_id is not a Canon location: {target_id!r}"
                    )
                patch["locations"]["state_updates"].append(
                    {"id": target_id, "current_state": value}
                )
            elif operation == "set_artifact_condition":
                if target_id not in artifact_ids:
                    raise RuntimeContractError(
                        f"canon_updates[{index}].target_id is not a Canon artifact: {target_id!r}"
                    )
                patch["artifacts"]["condition_updates"].append(
                    {"id": target_id, "condition": value}
                )
            elif operation == "transfer_artifact":
                holder_id = update.get("holder_id")
                if target_id not in artifact_ids or holder_id not in character_ids:
                    raise RuntimeContractError(
                        f"canon_updates[{index}] requires existing artifact target_id and character holder_id"
                    )
                patch["artifacts"]["custody_updates"].append(
                    {"id": target_id, "custody": {"kind": "character", "id": holder_id}}
                )
            else:
                raise RuntimeContractError(
                    f"canon_updates[{index}].operation is not supported: {operation!r}"
                )
        return patch

    def _scene_from_generated_payload(
        self,
        raw_scene: dict[str, Any],
        *,
        canon: Canon,
        volume: int,
        chapter: int,
        ordinal: int,
    ) -> tuple[SceneDesign, dict[str, Any]]:
        """Resolve an LLM narrative scene into one typed, Canon-scoped design."""
        try:
            pov_id = self._require_canon_id(canon, "character", raw_scene["pov_character_id"])
            setting_id = self._require_canon_id(canon, "location", raw_scene["location_id"])
            raw_cast_ids = raw_scene["character_ids"]
            if not isinstance(raw_cast_ids, list):
                raise RuntimeContractError("scene character_ids must be an array")
            cast_ids = {self._require_canon_id(canon, "character", value) for value in raw_cast_ids}
            cast_ids.add(pov_id)
            patch = self._compile_scene_updates(canon, raw_scene["canon_updates"])
        except KeyError as exc:
            raise RuntimeContractError(
                f"scene generation is missing required field: {exc.args[0]}"
            ) from exc

        scope = ContextScope(
            pov_character=EntityRef(kind="character", id=pov_id),
            setting=EntityRef(kind="location", id=setting_id),
            required_refs=[
                EntityRef(kind="character", id=character_id)
                for character_id in sorted(cast_ids - {pov_id})
            ],
        )
        design = SceneDesign(
            scene_id=f"scn_v{volume:03d}_c{chapter:03d}_s{ordinal:03d}",
            source_location=SceneLocation(volume=volume, chapter=chapter, ordinal=ordinal),
            chapter_number=chapter,
            scene_number=ordinal,
            title=str(raw_scene.get("title", "")),
            goal=str(raw_scene.get("goal", "")),
            conflict=str(raw_scene.get("conflict", "")),
            outcome=str(raw_scene.get("outcome", "")),
            turning_point=str(raw_scene.get("turning_point", "")),
            ending_hook=str(raw_scene.get("ending_hook", "")),
            key_events=[str(item) for item in raw_scene.get("key_events", [])],
            context_scope=scope,
            cast=[
                CastCharacter(character=EntityRef(kind="character", id=character_id))
                for character_id in sorted(cast_ids)
            ],
        )
        return design, patch

    def generate_volume_design(self, *, volume: int, plan: dict[str, Any]) -> SelectionSnapshot:
        """Generate and accept a volume via typed scenes and Canon events.

        Each LLM scene must supply a Canon patch candidate.  The candidate is
        never selected directly: it is resolved to stable IDs, projected,
        reviewed and accepted only by :meth:`accept_scene_design`.
        """
        volume_title = (
            plan.get("planned_volumes", [{}])[volume - 1].get("title", f"第{volume}巻")
            if plan.get("planned_volumes")
            else f"第{volume}巻"
        )
        previous_design = (
            self._payload(f"design.vol{volume - 1:02d}")
            if volume > 1 and f"design.vol{volume - 1:02d}" in self.snapshot.slots
            else None
        )
        volume_attempt, volume_design = self._run_task(
            "design.volume.generate",
            {
                "series_plan": plan,
                "volume_number": volume,
                "volume_title": volume_title,
                "genre": plan.get("genre", []),
                "previous_design": previous_design,
                "canon_context": self._design_author_context(self.load_canon()),
            },
            reason="generate volume skeleton",
        )
        volume_attempt, volume_design = self._review_and_revise(
            "design.volume",
            volume_design,
            volume_attempt,
            review_values=lambda candidate: {
                "series_plan": plan,
                "design": candidate,
                "canon_context": self._design_author_context(self.load_canon()),
            },
            revise_values=lambda candidate, review: {
                "series_plan": plan,
                "current_volume": candidate,
                "review": review,
                "canon_context": self._design_author_context(self.load_canon()),
            },
        )
        if not isinstance(volume_design.get("chapters"), list) or not volume_design["chapters"]:
            raise RuntimeContractError("volume design must contain at least one chapter")

        plan_ref = self._selected("plan.series")
        self._commit_task_result(
            volume_attempt,
            task_id="design.volume.generate",
            artifact_type="design.volume.candidate",
            logical_key=f"design.vol{volume:02d}.skeleton",
            payload=volume_design,
            payload_name=f"design.vol{volume:02d}.skeleton.json",
            input_artifact_ids=(plan_ref.artifact_id,),
        )
        generated_chapters: list[dict[str, Any]] = []
        applied_scenes: list[dict[str, Any]] = []
        previous_chapter_outcome = ""
        previous_scene_outcome = ""
        ordinal = 0

        for chapter_number, chapter_seed in enumerate(volume_design["chapters"], start=1):
            if not isinstance(chapter_seed, dict):
                raise RuntimeContractError("volume chapter seed must be an object")
            chapter_attempt, chapter_design = self._run_task(
                "design.chapter.generate",
                {
                    "series_plan": plan,
                    "volume_number": volume,
                    "volume_title": volume_title,
                    "volume_premise": volume_design.get("premise", ""),
                    "chapter_number": chapter_number,
                    "chapter_title": chapter_seed.get("title", ""),
                    "chapter_purpose": chapter_seed.get("purpose", ""),
                    "previous_chapter_outcome": previous_chapter_outcome,
                    "previous_volume_summary": previous_design,
                    "canon_context": self._design_author_context(self.load_canon()),
                },
                reason=f"generate chapter {chapter_number}",
            )
            chapter_attempt, chapter_design = self._review_and_revise(
                "design.chapter",
                chapter_design,
                chapter_attempt,
                review_values=lambda candidate: {
                    "series_plan": plan,
                    "design": candidate,
                    "canon_context": self._design_author_context(self.load_canon()),
                },
                revise_values=lambda candidate, review: {
                    "series_plan": plan,
                    "current_chapter": candidate,
                    "review": review,
                    "canon_context": self._design_author_context(self.load_canon()),
                },
            )
            if not isinstance(chapter_design.get("scenes"), list) or not chapter_design["scenes"]:
                raise RuntimeContractError(
                    f"chapter {chapter_number} must contain at least one scene"
                )
            self._commit_task_result(
                chapter_attempt,
                task_id="design.chapter.generate",
                artifact_type="design.chapter.candidate",
                logical_key=f"design.vol{volume:02d}.ch{chapter_number:02d}.candidate",
                payload=chapter_design,
                payload_name=f"design.vol{volume:02d}.ch{chapter_number:02d}.candidate.json",
                input_artifact_ids=(plan_ref.artifact_id,),
            )
            generated_chapters.append(chapter_design)

            for chapter_scene_number, scene_seed in enumerate(chapter_design["scenes"], start=1):
                if not isinstance(scene_seed, dict):
                    raise RuntimeContractError("chapter scene seed must be an object")
                ordinal += 1
                scene_attempt, raw_scene = self._run_task(
                    "design.scene.generate",
                    {
                        "series_plan": plan,
                        "volume_number": volume,
                        "volume_title": volume_title,
                        "volume_premise": volume_design.get("premise", ""),
                        "chapter_number": chapter_number,
                        "chapter_title": chapter_design.get("title", ""),
                        "chapter_purpose": chapter_design.get("purpose", ""),
                        "chapter_theme": chapter_design.get("theme", ""),
                        "chapter_emotional_arc": chapter_design.get("emotional_arc", ""),
                        "chapter_foreshadowing_notes": chapter_design.get(
                            "foreshadowing_notes", []
                        ),
                        "chapter_subplot_notes": chapter_design.get("subplot_notes", []),
                        "scene_number": ordinal,
                        "scene_count": ordinal,
                        "chapter_scene_number": chapter_scene_number,
                        "chapter_scene_count": len(chapter_design["scenes"]),
                        "scene_seed": scene_seed,
                        "previous_outcome": previous_scene_outcome,
                        "previous_volume_summary": previous_design,
                        "canon_context": self._design_author_context(self.load_canon()),
                    },
                    reason=f"generate scene {chapter_number}/{chapter_scene_number}",
                )
                canon = self.load_canon()

                def scene_contract(
                    candidate: dict[str, Any],
                    *,
                    _canon: Canon = canon,
                    _chapter_number: int = chapter_number,
                    _ordinal: int = ordinal,
                ) -> list[dict[str, Any]]:
                    try:
                        self._scene_from_generated_payload(
                            candidate,
                            canon=_canon,
                            volume=volume,
                            chapter=_chapter_number,
                            ordinal=_ordinal,
                        )
                    except RuntimeContractError as exc:
                        return [
                            {"severity": "error", "category": "canon_contract", "message": str(exc)}
                        ]
                    return []

                def scene_review_values(
                    candidate: dict[str, Any], *, _canon: Canon = canon, _seed: dict[str, Any] = scene_seed
                ) -> dict[str, Any]:
                    return {
                        "series_plan": plan,
                        "design": candidate,
                        "scene_seed": _seed,
                        "canon_context": self._design_author_context(_canon),
                    }

                def scene_revise_values(
                    candidate: dict[str, Any], review: dict[str, Any], *, _canon: Canon = canon, _seed: dict[str, Any] = scene_seed
                ) -> dict[str, Any]:
                    return {
                        "series_plan": plan,
                        "current_scene": candidate,
                        "review": review,
                        "scene_seed": _seed,
                        "canon_context": self._design_author_context(_canon),
                    }

                scene_attempt, raw_scene = self._review_and_revise(
                    "design.scene",
                    raw_scene,
                    scene_attempt,
                    review_values=scene_review_values,
                    revise_values=scene_revise_values,
                    contract_issues=scene_contract,
                )
                design, patch = self._scene_from_generated_payload(
                    raw_scene,
                    canon=canon,
                    volume=volume,
                    chapter=chapter_number,
                    ordinal=ordinal,
                )
                self._commit_task_result(
                    scene_attempt,
                    task_id="design.scene.generate",
                    artifact_type="design.scene.candidate",
                    logical_key=f"design.vol{volume:02d}.ch{chapter_number:02d}.sc{chapter_scene_number:02d}.candidate",
                    payload=raw_scene,
                    payload_name=f"design.vol{volume:02d}.ch{chapter_number:02d}.sc{chapter_scene_number:02d}.candidate.json",
                    input_artifact_ids=(plan_ref.artifact_id,),
                )
                _snapshot, applied = self.accept_scene_design(design, patch)
                applied_scenes.append(applied.model_dump(mode="json"))
                previous_scene_outcome = applied.outcome
            previous_chapter_outcome = str(chapter_design.get("outcome", ""))

        return self.publish_design(
            volume,
            {
                **volume_design,
                "chapters": generated_chapters,
                "scenes": applied_scenes,
            },
        )

    @staticmethod
    def _writer_context(raw_scene: dict[str, Any]) -> dict[str, Any]:
        """Return the only design-derived payload allowed to cross the writer boundary."""
        try:
            writer_context = WriterContext.model_validate(raw_scene["writer_context"])
        except KeyError as exc:
            raise RuntimeContractError("design scene is missing required writer_context") from exc
        except ValidationError as exc:
            raise RuntimeContractError("design scene has invalid writer_context") from exc
        return writer_context.model_dump(mode="json")

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
            writer_context = self._writer_context(raw_scene)
            chapter = int(raw_scene["chapter_number"])
            scene = int(raw_scene["scene_number"])
            stem = f"write.vol{volume:02d}.ch{chapter:02d}.sc{scene:02d}"
            draft_attempt, draft = self._run_task(
                "write.draft.generate",
                {"writer_context": writer_context, "previous_summary": previous_summary},
                reason="draft generation",
            )
            draft_ref = self._commit_task_result(
                draft_attempt,
                task_id="write.draft.generate",
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
                    {
                        "writer_context": writer_context,
                        "draft": self.repository.read_payload(final_draft),
                    },
                    reason=f"draft review {cycle + 1}",
                )
                issues = review.get("issues", [])
                review_key = (
                    f"{stem}.final_review"
                    if not issues or cycle + 1 == self.max_review_count
                    else f"{stem}.draft_review.{cycle + 1}"
                )
                final_review = self._commit_task_result(
                    review_attempt,
                    task_id="write.draft.review",
                    artifact_type="review.issues",
                    logical_key=review_key,
                    payload=review,
                    payload_name=f"{review_key}.json",
                    input_artifact_ids=(final_draft.artifact_id,),
                )
                if not issues:
                    break
                if cycle + 1 == self.max_review_count:
                    break
                revise_attempt, revised = self._run_task(
                    "write.draft.revise",
                    {
                        "writer_context": writer_context,
                        "draft": self.repository.read_payload(final_draft),
                        "review": review,
                    },
                    reason=f"draft revise {cycle + 1}",
                )
                final_draft = self._commit_task_result(
                    revise_attempt,
                    task_id="write.draft.revise",
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
                selected_attempt = self._attempt(
                    "write.draft.revise", "commit final selected draft"
                )
                final_draft = self.repository.commit_artifact(
                    selected_attempt,
                    artifact_type="write.draft",
                    logical_key=f"{stem}.draft",
                    payload=self.repository.read_payload(final_draft),
                    payload_name=f"{stem}.draft.final.json",
                    input_artifact_ids=(final_draft.artifact_id,),
                    quality_status="passed",
                )
            summary_ref, summary_review = self._make_summary(
                writer_context, final_draft, previous_summary, stem
            )
            snapshot = self._publish(
                {
                    f"{stem}.draft": final_draft.artifact_id,
                    f"{stem}.final_review": final_review.artifact_id,
                    f"{stem}.summary": summary_ref.artifact_id,
                },
                f"write scene {volume}/{chapter}/{scene} accepted",
            )
            previous_summary = self._writer_handoff(self.repository.read_payload(summary_ref))
        return WorkflowResult(snapshot.selection_snapshot_id)

    def _make_summary(
        self,
        writer_context: dict[str, Any],
        draft_ref: ArtifactReference,
        previous_summary: dict[str, Any] | None,
        stem: str,
    ) -> tuple[ArtifactReference, ArtifactReference]:
        draft = self.repository.read_payload(draft_ref)
        generate_attempt, candidate = self._run_task(
            "write.summary.generate",
            {
                "writer_context": writer_context,
                "draft": draft,
                "previous_summary": previous_summary,
            },
            reason="summary generation",
        )
        candidate_ref = self._commit_task_result(
            generate_attempt,
            task_id="write.summary.generate",
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
                task_id="write.summary.review",
                artifact_type="review.issues",
                logical_key=f"{stem}.summary_review.{cycle + 1}",
                payload=review,
                payload_name=f"{stem}.summary_review.{cycle + 1}.json",
                input_artifact_ids=(draft_ref.artifact_id, final.artifact_id),
            )
            if not review.get("issues"):
                break
            if cycle + 1 == self.max_summary_review_count:
                break
            revise_attempt, revised = self._run_task(
                "write.summary.revise",
                {"draft": draft, "summary": self.repository.read_payload(final), "review": review},
                reason=f"summary revise {cycle + 1}",
            )
            final = self._commit_task_result(
                revise_attempt,
                task_id="write.summary.revise",
                artifact_type="write.summary",
                logical_key=f"{stem}.summary_candidate.{cycle + 2}",
                payload=revised,
                payload_name=f"{stem}.summary_candidate.{cycle + 2}.json",
                input_artifact_ids=(draft_ref.artifact_id, final_review.artifact_id),
            )
        if final_review is None:
            raise RuntimeContractError("summary review was not recorded")
        status: Literal["passed"] = "passed"
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

    def export_volume(
        self, volume: int, *, format: Literal["json", "markdown"] = "json"
    ) -> dict[str, Any]:
        if format not in {"json", "markdown"}:
            raise RuntimeContractError(f"unsupported export format: {format}")
        design = self._payload(f"design.vol{volume:02d}")
        scenes = design.get("scenes")
        if not isinstance(scenes, list):
            raise RuntimeContractError("selected design has no scenes")
        contents: list[str] = []
        volume_title = str(design.get("title") or f"第{volume}巻")
        markdown_parts = [f"# {volume_title}"]
        current_chapter: int | None = None
        input_ids: set[str] = {
            self._selected("plan.series").artifact_id,
            self._selected(f"design.vol{volume:02d}").artifact_id,
            self._selected("canon.seed").artifact_id,
            self._selected("canon.frontier").artifact_id,
        }
        review_report: list[dict[str, Any]] = []
        for raw_scene in scenes:
            chapter = int(raw_scene["chapter_number"])
            scene = int(raw_scene["scene_number"])
            stem = f"write.vol{volume:02d}.ch{chapter:02d}.sc{scene:02d}"
            draft_ref = self._selected(f"{stem}.draft")
            summary_ref = self._selected(f"{stem}.summary")
            final_review_ref = self._selected(f"{stem}.final_review")
            draft = self.repository.read_payload(draft_ref)
            draft_content = str(draft.get("content", ""))
            contents.append(draft_content)
            if chapter != current_chapter:
                markdown_parts.append(f"## 第{chapter}章")
                current_chapter = chapter
            scene_title = str(raw_scene.get("title") or f"シーン {scene}")
            markdown_parts.extend((f"### {scene_title}", draft_content))
            input_ids.update(
                (draft_ref.artifact_id, summary_ref.artifact_id, final_review_ref.artifact_id)
            )
            summary_review_id = summary_ref.manifest.metadata.get("summary_review_artifact_id")
            if isinstance(summary_review_id, str):
                input_ids.add(summary_review_id)
            review_report.append(
                {
                    "scene": f"{chapter}/{scene}",
                    "draft_review": self.repository.read_payload(final_review_ref),
                    "summary_quality_status": summary_ref.manifest.quality_status,
                    "summary_review_artifact_id": summary_review_id,
                }
            )
        manuscript = {
            "content": "\n\n---\n\n".join(contents),
            "volume": volume,
            "canon": self.load_canon().model_dump(mode="json"),
            "review_report": review_report,
        }
        if format == "markdown":
            content = "\n\n".join(markdown_parts).strip() + "\n"
            ref = self._artifact(
                task_id="write.export.generate",
                reason="render pinned markdown manuscript",
                artifact_type="export.manuscript.markdown",
                logical_key=f"export.vol{volume:02d}.manuscript.markdown",
                payload=content,
                payload_name=f"export.vol{volume:02d}.manuscript.md",
                input_artifact_ids=tuple(input_ids),
                metadata={"input_snapshot_id": self.snapshot.selection_snapshot_id, "format": format},
            )
            return {
                "content": content,
                "volume": volume,
                "format": format,
                "artifact_id": ref.artifact_id,
                "input_snapshot_id": self.snapshot.selection_snapshot_id,
            }

        ref = self._artifact(
            task_id="write.export.generate",
            reason="assemble pinned manuscript",
            artifact_type="export.manuscript",
            logical_key=f"export.vol{volume:02d}.manuscript",
            payload=manuscript,
            payload_name=f"export.vol{volume:02d}.manuscript.json",
            input_artifact_ids=tuple(input_ids),
            metadata={"input_snapshot_id": self.snapshot.selection_snapshot_id, "format": format},
        )
        return {
            **manuscript,
            "format": format,
            "artifact_id": ref.artifact_id,
            "input_snapshot_id": self.snapshot.selection_snapshot_id,
        }
