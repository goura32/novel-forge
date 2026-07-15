"""RED tests for deterministic artifacts prepared around one PNCA Scene Contract."""

from pathlib import Path
from typing import Any

from novel_forge.pnca.contracts import (
    ChapterContract,
    FrontierBinding,
    SceneContract,
    VolumeContract,
)
from novel_forge.pnca.progression import AuthoredContract
from novel_forge.pnca.scene_preparation import PNCASceneStructurePreparer
from novel_forge.runtime import RunRepository
from tests.pnca_fixtures import chapter_plan, scene_slot, writer_view


def _artifact(
    repo: RunRepository,
    run: Any,
    *,
    artifact_type: str,
    logical_key: str,
    payload: object,
    **kwargs: Any,
) -> Any:
    attempt = repo.start_attempt(run, task_id="pnca.test", phase="pnca", reason="test")
    return repo.commit_artifact(
        attempt,
        artifact_type=artifact_type,
        logical_key=logical_key,
        payload=payload,
        payload_name=f"{logical_key.replace('.', '_')}.json",
        **kwargs,
    )


def test_prepare_mutating_scene_structure_pins_all_deterministic_roles(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    root_run = repo.create_run(command="plan", model="fake", verbose=False)
    seed = _artifact(repo, root_run, artifact_type="canon.seed", logical_key="canon.seed", payload={"seed": True})
    frontier = _artifact(
        repo,
        root_run,
        artifact_type="canon.event_set",
        logical_key="canon.frontier.root",
        payload={"events": []},
        canon_lineage_root_digest=seed.manifest.content_digest,
    )
    snapshot = repo.create_selection_snapshot(
        slug="series_001",
        slots={"canon.seed": seed.artifact_id, "canon.frontier": frontier.artifact_id},
        reason="bootstrap",
    )
    run = repo.create_run(
        command="design",
        model="fake",
        verbose=False,
        input_snapshot_id=snapshot.selection_snapshot_id,
    )
    common = {
        "canon_lineage_root_digest": seed.manifest.content_digest,
        "input_canon_frontier_digest": frontier.manifest.content_digest,
        "input_artifact_ids": (frontier.artifact_id,),
    }
    volume_contract = VolumeContract(
        contract_id="volume_001",
        parent_series_contract_id="series_001",
        volume_ordinal=1,
    )
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
        chapter_plan=chapter_plan(), scene_slots=(scene_slot(),),
    )
    chapter = _artifact(
        repo,
        run,
        artifact_type="pnca.chapter.contract",
        logical_key="pnca.chapter.contract.series_001.001.001",
        payload=chapter_contract.model_dump(mode="json"),
        input_artifact_ids=(volume.artifact_id, frontier.artifact_id),
        canon_lineage_root_digest=seed.manifest.content_digest,
        input_canon_frontier_digest=frontier.manifest.content_digest,
    )
    binding = FrontierBinding(
        input_snapshot_id=snapshot.selection_snapshot_id,
        frontier_artifact_id=frontier.artifact_id,
        frontier_digest=frontier.manifest.content_digest,
        lineage_root_digest=seed.manifest.content_digest,
    )
    scene_contract = SceneContract(
        contract_id="scene_contract_001",
        slot_id="scene_001",
        frontier_binding=binding,
        canon_effect="mutates",
        canon_patch={
            "entity_id": "character_lina", "state_key": "knowledge", "prior_value": "未確認",
            "new_value": "確認済み", "cause_beat_index": 0,
            "observable_consequence": "塔の扉の印を確認する",
        },
        writer_view=writer_view(),
    )
    scene = _artifact(
        repo,
        run,
        artifact_type="pnca.scene.contract",
        logical_key="pnca.scene.contract.series_001.001.001.scene_001",
        payload=scene_contract.model_dump(mode="json"),
        input_artifact_ids=(chapter.artifact_id, frontier.artifact_id),
        canon_lineage_root_digest=seed.manifest.content_digest,
        input_canon_frontier_digest=frontier.manifest.content_digest,
    )

    prepared = PNCASceneStructurePreparer(repository=repo).prepare(
        slug="series_001",
        run=run,
        scene=AuthoredContract(artifact=scene, contract=scene_contract),
        parent_chapter=AuthoredContract(artifact=chapter, contract=chapter_contract),
        parent_volume=AuthoredContract(artifact=volume, contract=volume_contract),
    )

    assert prepared.frontier_output.artifact_id != frontier.artifact_id
    assert prepared.frontier_output.manifest.parent_frontier_artifact_id == frontier.artifact_id
    assert set(prepared.role_artifact_ids) == {
        "scene.contract",
        "parent.requirement_ledger",
        "accepted.requirement_ledger",
        "scene.slot_binding",
        "canon.frontier.output",
    }
    parent_ledger = repo.read_payload(prepared.parent_requirement_ledger)
    assert parent_ledger == {"owner_contract_id": "chapter_001", "requirements": []}
    accepted_ledger = repo.read_payload(prepared.accepted_requirement_ledger)
    assert accepted_ledger["owner_contract_id"] == "scene_contract_001"
    assert accepted_ledger["parent_ledger_artifact_id"] == prepared.parent_requirement_ledger.artifact_id
    assert accepted_ledger["dispositions"] == []
    slot_binding = repo.read_payload(prepared.slot_binding)
    assert slot_binding == {
        "chapter_contract_id": "chapter_001",
        "scene_contract_id": "scene_contract_001",
        "slot_id": "scene_001",
    }
    for role in (prepared.parent_requirement_ledger, prepared.accepted_requirement_ledger, prepared.slot_binding):
        assert role.manifest.input_canon_frontier_digest == frontier.manifest.content_digest
        assert role.manifest.canon_lineage_root_digest == seed.manifest.content_digest
