"""Integration test: a complete non-mutating Scene acceptance group is committed atomically."""

from __future__ import annotations

from pathlib import Path

from novel_forge.pnca.contracts import (
    ChapterContract,
    FrontierBinding,
    SceneContract,
    SceneSlot,
    VolumeContract,
)
from novel_forge.pnca.progression import AuthoredContract
from novel_forge.pnca.workflow import PNCAWorkflow
from novel_forge.runtime import RunRepository


def _artifact(repo, run, *, artifact_type, logical_key, payload, **manifest_kwargs):
    attempt = repo.start_attempt(run, task_id="pnca.test", phase="pnca", reason="test")
    return repo.commit_artifact(
        attempt,
        artifact_type=artifact_type,
        logical_key=logical_key,
        payload=payload,
        payload_name=f"{logical_key.replace('.', '_')}.json",
        **manifest_kwargs,
    )


def _bootstrap(repo):
    run = repo.create_run(command="plan", model="fake", verbose=False)
    seed = _artifact(repo, run, artifact_type="canon.seed", logical_key="canon.seed", payload={"seed": True})
    root = _artifact(
        repo,
        run,
        artifact_type="canon.event_set",
        logical_key="canon.frontier.root",
        payload={"events": []},
        canon_lineage_root_digest=seed.manifest.content_digest,
    )
    snapshot = repo.create_selection_snapshot(
        slug="series",
        slots={"canon.seed": seed.artifact_id, "canon.frontier": root.artifact_id},
        reason="pnca-bootstrap",
    )
    return run, seed, root, snapshot


def test_build_and_commit_non_mutating_scene_acceptance_group(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    run, seed, root, base = _bootstrap(repo)
    common = {
        "canon_lineage_root_digest": seed.manifest.content_digest,
        "input_canon_frontier_digest": root.manifest.content_digest,
        "input_artifact_ids": (root.artifact_id,),
    }
    volume_contract = VolumeContract(contract_id="volume_001", parent_series_contract_id="series_001", volume_ordinal=1)
    volume = _artifact(
        repo,
        run,
        artifact_type="pnca.volume.contract",
        logical_key="pnca.volume.contract.series_001.001",
        payload=volume_contract.model_dump(mode="json"),
        **common,
    )
    chapter_contract = ChapterContract(
        contract_id="chapter_001",
        parent_volume_contract_id=volume_contract.contract_id,
        chapter_ordinal=1,
        scene_slots=(SceneSlot(slot_id="scene_001", ordinal=1),),
    )
    chapter = _artifact(
        repo,
        run,
        artifact_type="pnca.chapter.contract",
        logical_key="pnca.chapter.contract.series_001.001.001",
        payload=chapter_contract.model_dump(mode="json"),
        input_artifact_ids=(volume.artifact_id, root.artifact_id),
        canon_lineage_root_digest=seed.manifest.content_digest,
        input_canon_frontier_digest=root.manifest.content_digest,
    )
    binding = FrontierBinding(
        input_snapshot_id=base.selection_snapshot_id,
        frontier_artifact_id=root.artifact_id,
        frontier_digest=root.manifest.content_digest,
        lineage_root_digest=seed.manifest.content_digest,
    )
    scene_contract = SceneContract(
        contract_id="scene_contract_001",
        slot_id="scene_001",
        frontier_binding=binding,
        canon_effect="none",
    )
    scene = _artifact(
        repo,
        run,
        artifact_type="pnca.scene.contract",
        logical_key="pnca.scene.contract.series_001.001.001.scene_001",
        payload=scene_contract.model_dump(mode="json"),
        input_artifact_ids=(chapter.artifact_id, root.artifact_id),
        canon_lineage_root_digest=seed.manifest.content_digest,
        input_canon_frontier_digest=root.manifest.content_digest,
    )

    workflow = PNCAWorkflow(repository=repo, contract_author=object())
    acceptance = workflow.build_scene_acceptance(
        slug="series",
        run=run,
        scene=AuthoredContract(artifact=scene, contract=scene_contract),
        parent_chapter=AuthoredContract(artifact=chapter, contract=chapter_contract),
        parent_volume=AuthoredContract(artifact=volume, contract=volume_contract),
        frontier_binding=binding,
        base_snapshot_id=base.selection_snapshot_id,
    )

    assert acceptance.canon_effect == "none"
    assert set(acceptance.role_artifact_ids) == {
        "scene.contract",
        "parent.requirement_ledger",
        "accepted.requirement_ledger",
        "audit.batch",
        "review.synthesis",
        "scene.slot_binding",
        "canon.frontier.output",
    }

    snapshot = repo.commit_pnca_acceptance(slug="series", acceptance=acceptance, frontier_binding=binding)
    assert snapshot.slots["pnca.scene.contract.series_001.001.001.scene_001"] == scene.artifact_id
    assert snapshot.slots["canon.frontier"] == root.artifact_id
    assert snapshot.slots["pnca.audit.batch.scene_contract_001"] == acceptance.role_artifact_ids["audit.batch"]
