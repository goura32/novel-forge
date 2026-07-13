"""Deterministic production artifacts prepared around one PNCA Scene Contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from novel_forge.pnca.contracts import (
    AdmissionConsumption,
    ChapterContract,
    ParentRequirementLedger,
    SceneContract,
    VolumeContract,
)
from novel_forge.pnca.progression import AuthoredContract
from novel_forge.pnca.validation import validate_scene_structure
from novel_forge.runtime import ArtifactReference, RunHandle, RunRepository, RuntimeContractError


@dataclass(frozen=True, slots=True)
class PreparedSceneStructure:
    """Deterministic roles available before audit/review synthesis."""

    scene_contract: ArtifactReference
    parent_requirement_ledger: ArtifactReference
    accepted_requirement_ledger: ArtifactReference
    slot_binding: ArtifactReference
    frontier_output: ArtifactReference

    @property
    def role_artifact_ids(self) -> dict[str, str]:
        return {
            "scene.contract": self.scene_contract.artifact_id,
            "parent.requirement_ledger": self.parent_requirement_ledger.artifact_id,
            "accepted.requirement_ledger": self.accepted_requirement_ledger.artifact_id,
            "scene.slot_binding": self.slot_binding.artifact_id,
            "canon.frontier.output": self.frontier_output.artifact_id,
        }


class PNCASceneStructurePreparer:
    """Materialize scene acceptance structure without making narrative judgements."""

    def __init__(self, *, repository: RunRepository) -> None:
        self.repository = repository

    def prepare(
        self,
        *,
        slug: str,
        run: RunHandle,
        scene: AuthoredContract[SceneContract],
        parent_chapter: AuthoredContract[ChapterContract],
        parent_volume: AuthoredContract[VolumeContract],
    ) -> PreparedSceneStructure:
        contract = scene.contract
        binding = contract.frontier_binding
        if parent_chapter.contract.parent_volume_contract_id != parent_volume.contract.contract_id:
            raise RuntimeContractError("ChapterContract does not bind the supplied parent VolumeContract")
        if contract.slot_id not in {slot.slot_id for slot in parent_chapter.contract.scene_slots}:
            raise RuntimeContractError("SceneContract slot is not allocated by the supplied ChapterContract")

        snapshot = self.repository.load_snapshot(slug, binding.input_snapshot_id)
        if snapshot.slots.get("canon.frontier") != binding.frontier_artifact_id:
            raise RuntimeContractError("SceneContract FrontierBinding must reference the selected snapshot frontier")
        frontier = self.repository.verify_artifact(binding.frontier_artifact_id)
        if frontier.manifest.content_digest != binding.frontier_digest:
            raise RuntimeContractError("SceneContract FrontierBinding digest does not match its frontier artifact")

        parent_ledger = ParentRequirementLedger(
            owner_contract_id=parent_chapter.contract.contract_id,
            requirements=(),
        )
        prior_consumptions = self._prior_admission_consumptions(
            slug=slug,
            input_snapshot_id=binding.input_snapshot_id,
            parent_chapter_artifact_id=parent_chapter.artifact.artifact_id,
        )
        validate_scene_structure(
            contract=contract,
            parent_ledger=parent_ledger,
            scene_slots=parent_chapter.contract.scene_slots,
            admission_allowances=parent_volume.contract.admission_allowances,
            consumed_admissions=prior_consumptions,
        )

        provenance = {
            "input_artifact_ids": (
                parent_volume.artifact.artifact_id,
                parent_chapter.artifact.artifact_id,
                scene.artifact.artifact_id,
                frontier.artifact_id,
            ),
            "canon_lineage_root_digest": binding.lineage_root_digest,
            "input_canon_frontier_digest": binding.frontier_digest,
        }
        parent_ref = self._commit(
            run=run,
            task_id="pnca.scene.parent_requirement_ledger",
            artifact_type="pnca.parent_requirement_ledger",
            logical_key=f"pnca.ledger.parent.{contract.contract_id}",
            payload=parent_ledger.model_dump(mode="json"),
            payload_name="parent_requirement_ledger.json",
            provenance=provenance,
        )
        accepted_ref = self._commit(
            run=run,
            task_id="pnca.scene.accepted_requirement_ledger",
            artifact_type="pnca.accepted_requirement_ledger",
            logical_key=f"pnca.ledger.accepted.{contract.contract_id}",
            payload={
                "owner_contract_id": contract.contract_id,
                "parent_ledger_artifact_id": parent_ref.artifact_id,
                "dispositions": [item.model_dump(mode="json") for item in contract.requirement_dispositions],
            },
            payload_name="accepted_requirement_ledger.json",
            provenance={**provenance, "input_artifact_ids": (*provenance["input_artifact_ids"], parent_ref.artifact_id)},
        )
        slot_ref = self._commit(
            run=run,
            task_id="pnca.scene.slot_binding",
            artifact_type="pnca.scene.slot_binding",
            logical_key=f"pnca.scene.slot.{contract.contract_id}",
            payload={
                "chapter_contract_id": parent_chapter.contract.contract_id,
                "scene_contract_id": contract.contract_id,
                "slot_id": contract.slot_id,
            },
            payload_name="slot_binding.json",
            provenance=provenance,
        )
        frontier_output = frontier
        if contract.canon_effect == "mutates":
            patch_ref = self._commit(
                run=run,
                task_id="pnca.scene.canon_patch",
                artifact_type="canon.patch",
                logical_key=f"canon.patch.{contract.contract_id}",
                payload={"scene_contract_id": contract.contract_id, "patch": contract.canon_patch},
                payload_name="canon_patch.json",
                provenance=provenance,
            )
            events = [
                {"kind": "scene_patch", "scene_contract_id": contract.contract_id, "patch": contract.canon_patch},
                *[
                    {
                        "kind": "entity_admission",
                        "entity_id": item.entity_id,
                        "entity_kind": item.kind,
                        "allowance_id": item.allowance_id,
                        "scene_contract_id": contract.contract_id,
                    }
                    for item in contract.admission_consumptions
                ],
            ]
            attempt = self.repository.start_attempt(
                run, task_id="pnca.scene.canon_frontier", phase="design", reason="materialize canonical scene patch"
            )
            frontier_output = self.repository.commit_artifact(
                attempt,
                artifact_type="canon.event_set",
                logical_key=f"canon.frontier.{contract.contract_id}",
                payload={"events": events},
                payload_name="frontier.json",
                input_artifact_ids=(*provenance["input_artifact_ids"], patch_ref.artifact_id),
                canon_lineage_root_digest=binding.lineage_root_digest,
                input_canon_frontier_digest=binding.frontier_digest,
                parent_frontier_artifact_id=frontier.artifact_id,
                parent_frontier_digest=frontier.manifest.content_digest,
                source_patch_artifact_ids=(patch_ref.artifact_id,),
                metadata={
                    "source_scene_contract_artifact_id": scene.artifact.artifact_id,
                    "source_scene_contract_digest": scene.artifact.manifest.content_digest,
                },
            )
        return PreparedSceneStructure(
            scene_contract=scene.artifact,
            parent_requirement_ledger=parent_ref,
            accepted_requirement_ledger=accepted_ref,
            slot_binding=slot_ref,
            frontier_output=frontier_output,
        )

    def _prior_admission_consumptions(
        self, *, slug: str, input_snapshot_id: str, parent_chapter_artifact_id: str
    ) -> tuple[AdmissionConsumption, ...]:
        """Read only selected earlier Scene Contracts pinned to this Chapter artifact."""
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
        attempt = self.repository.start_attempt(run, task_id=task_id, phase="design", reason="prepare deterministic scene acceptance structure")
        return self.repository.commit_artifact(
            attempt,
            artifact_type=artifact_type,
            logical_key=logical_key,
            payload=payload,
            payload_name=payload_name,
            **provenance,
        )
