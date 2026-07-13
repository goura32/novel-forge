"""Deterministic scene audit batch and review synthesis for non-mutating scenes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from novel_forge.pnca.contracts import (
    AdmissionConsumption,
    ChapterContract,
    ParentRequirementLedger,
    SceneContract,
    SceneReviewSynthesis,
    SceneStructuralAudit,
    VolumeContract,
)
from novel_forge.pnca.progression import AuthoredContract
from novel_forge.pnca.validation import validate_scene_structure
from novel_forge.runtime import ArtifactReference, RunHandle, RunRepository, RuntimeContractError


@dataclass(frozen=True, slots=True)
class PreparedSceneAudit:
    """Provider-free structural audit evidence plus its synthesis artifact."""

    batch: ArtifactReference
    synthesis: ArtifactReference


class PNCASceneAuditSynthesizer:
    """Run only the deterministic structural audit; synthesis is precondition-free."""

    def __init__(self, *, repository: RunRepository) -> None:
        self.repository = repository

    def run_structural_audit(
        self,
        *,
        run: RunHandle,
        slug: str,
        scene: AuthoredContract[SceneContract],
        parent_chapter: AuthoredContract[ChapterContract],
        parent_volume: AuthoredContract[VolumeContract],
    ) -> PreparedSceneAudit:
        contract = scene.contract
        binding = contract.frontier_binding
        frontier = self.repository.verify_artifact(binding.frontier_artifact_id)
        if frontier.manifest.content_digest != binding.frontier_digest:
            raise RuntimeContractError("SceneContract FrontierBinding digest does not match its frontier artifact")

        prior_consumptions = self._prior_admission_consumptions(
            slug=slug,
            input_snapshot_id=binding.input_snapshot_id,
            parent_chapter_artifact_id=parent_chapter.artifact.artifact_id,
        )
        observations: list[dict[str, Any]] = []
        try:
            validate_scene_structure(
                contract=contract,
                parent_ledger=ParentRequirementLedger(
                    owner_contract_id=parent_chapter.contract.contract_id,
                    requirements=(),
                ),
                scene_slots=parent_chapter.contract.scene_slots,
                admission_allowances=parent_volume.contract.admission_allowances,
                consumed_admissions=prior_consumptions,
            )
        except Exception as exc:  # structural validation failure is evidence, not a crash
            observations.append({"level": "error", "code": "structural_violation", "detail": str(exc)})

        provenance: dict[str, Any] = {
            "input_artifact_ids": (
                parent_volume.artifact.artifact_id,
                parent_chapter.artifact.artifact_id,
                scene.artifact.artifact_id,
                frontier.artifact_id,
            ),
            "canon_lineage_root_digest": binding.lineage_root_digest,
            "input_canon_frontier_digest": binding.frontier_digest,
        }
        audit = SceneStructuralAudit(
            scene_contract_id=contract.contract_id,
            checks=(
                {"check": "slot_allocated", "passed": True},
                {"check": "frontier_binding", "passed": True},
                {"check": "structural_constraints", "passed": not observations},
            ),
            passed=not observations,
        )
        batch_ref = self._commit(
            run=run,
            task_id="pnca.scene.audit.batch",
            artifact_type="pnca.audit.batch",
            logical_key=f"pnca.audit.batch.{contract.contract_id}",
            payload=audit.model_dump(mode="json"),
            payload_name="audit_batch.json",
            provenance=provenance,
        )
        synthesis = SceneReviewSynthesis(
            scene_contract_id=contract.contract_id,
            audit_batch_artifact_id=batch_ref.artifact_id,
            observations=tuple(observations),
            passed=not observations,
        )
        synthesis_ref = self._commit(
            run=run,
            task_id="pnca.scene.review.synthesis",
            artifact_type="pnca.review.synthesis",
            logical_key=f"pnca.review.synthesis.{contract.contract_id}",
            payload=synthesis.model_dump(mode="json"),
            payload_name="review_synthesis.json",
            provenance={**provenance, "input_artifact_ids": (*provenance["input_artifact_ids"], batch_ref.artifact_id)},
        )
        return PreparedSceneAudit(batch=batch_ref, synthesis=synthesis_ref)

    def _prior_admission_consumptions(
        self, *, slug: str, input_snapshot_id: str, parent_chapter_artifact_id: str
    ) -> tuple[AdmissionConsumption, ...]:
        snapshot = self.repository.load_snapshot(slug, input_snapshot_id)
        consumptions: list[AdmissionConsumption] = []
        for artifact_id in snapshot.slots.values():
            artifact = self.repository.verify_artifact(artifact_id)
            if (
                artifact.manifest.artifact_type != "pnca.scene.contract"
                or parent_chapter_artifact_id not in artifact.manifest.input_artifact_ids
            ):
                continue
            prior = SceneContract.model_validate(self.repository.read_payload(artifact))
            consumptions.extend(prior.admission_consumptions)
        return tuple(consumptions)

    def _commit(
        self,
        *,
        run: RunHandle,
        task_id: str,
        artifact_type: str,
        logical_key: str,
        payload: dict[str, Any],
        payload_name: str,
        provenance: dict[str, Any],
    ) -> ArtifactReference:
        attempt = self.repository.start_attempt(run, task_id=task_id, phase="design", reason="prepare scene audit evidence")
        return self.repository.commit_artifact(
            attempt,
            artifact_type=artifact_type,
            logical_key=logical_key,
            payload=payload,
            payload_name=payload_name,
            **provenance,
        )
