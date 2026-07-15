"""Integration test: a complete non-mutating Scene acceptance group is committed atomically."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from novel_forge.pnca.contracts import (
    ChapterContract,
    FrontierBinding,
    SceneContract,
    VolumeContract,
)
from novel_forge.pnca.export import PNCAExporter
from novel_forge.pnca.progression import AuthoredContract
from novel_forge.pnca.workflow import PNCAWorkflow
from novel_forge.runtime import RunRepository, RuntimeContractError
from tests.pnca_fixtures import chapter_plan, scene_slot, writer_view


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


def test_build_rejects_non_mutating_scene_acceptance_group(tmp_path: Path) -> None:
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
        chapter_plan=chapter_plan(), scene_slots=(scene_slot(),),
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
        writer_view=writer_view(),
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
    with pytest.raises(RuntimeContractError, match="must mutate"):
        workflow.build_scene_acceptance(
            slug="series",
            run=run,
            scene=AuthoredContract(artifact=scene, contract=scene_contract),
            parent_chapter=AuthoredContract(artifact=chapter, contract=chapter_contract),
            parent_volume=AuthoredContract(artifact=volume, contract=volume_contract),
            frontier_binding=binding,
            base_snapshot_id=base.selection_snapshot_id,
        )


class FakeExecutor:
    """Provider-free executor stub for writer/export wiring tests."""

    def __init__(self, repository: RunRepository, *, audit_issues: list[dict[str, str]] | None = None) -> None:
        self._repo = repository
        self._audit_issues = audit_issues or []

    def execute(self, *, task_id: str, scope_id: str, artifacts: dict[str, Any], input_artifact_ids: tuple[str, ...]) -> Any:
        if task_id == "pnca.writer_view.review":
            return {"issues": []}
        if task_id == "pnca.scene.render":
            return {"content": "シーンの本文。約500字の自然な日本語で書く。"}
        if task_id == "pnca.scene.coverage":
            return {"evidence": [{"obligation": "required_beat", "beat_index": 0, "draft_quote": "シーンの本文"}, {"obligation": "end_constraint", "draft_quote": "シーンの本文"}]}
        if task_id == "pnca.draft.audit":
            return {"issues": self._audit_issues}
        if task_id == "pnca.scene.rerender":
            return {"content": "シーンの本文。約500字の自然な日本語で書く。", "coverage": {"evidence": [{"obligation": "required_beat", "beat_index": 0, "draft_quote": "シーンの本文"}, {"obligation": "end_constraint", "draft_quote": "シーンの本文"}]}}
        if task_id == "pnca.scene.revise":
            # Revise returns the same draft content (stub); the audit blocker loop re-audits.
            draft = artifacts.get("scene.draft", {})
            return {"content": draft.get("content", "シーンの本文。約500字の自然な日本語で書く。"), "coverage": {"evidence": []}}
        raise AssertionError(f"unexpected task_id: {task_id}")


@pytest.mark.parametrize(
    "audit_issues",
    [
        [],
        [{"severity": "major", "constraint_kind": "quality", "writer_view_field": "narrative_contract.style", "draft_quote": "シーンの本文", "detail": "語彙の反復"}],
        [{"severity": "blocker", "constraint_kind": "pov_fact", "writer_view_field": "presentation_constraints", "draft_quote": "シーンの本文", "detail": "可視の行為を誤ってPOV違反と評価した観察記録"}],
    ],
    ids=["clean_audit", "deferred_editorial_quality", "non_waivable_blocker"],
)
def test_write_volume_renders_and_exports_bundle(tmp_path: Path, audit_issues: list[dict[str, str]]) -> None:
    repo = RunRepository(tmp_path)
    run, seed, root, base = _bootstrap(repo)
    slug = "series_001"
    common = {
        "canon_lineage_root_digest": seed.manifest.content_digest,
        "input_canon_frontier_digest": root.manifest.content_digest,
        "input_artifact_ids": (root.artifact_id,),
    }
    volume_contract = VolumeContract(contract_id="volume_001", parent_series_contract_id="series_001", volume_ordinal=1)
    volume = _artifact(
        repo, run, artifact_type="pnca.volume.contract",
        logical_key="pnca.volume.contract.series_001.001",
        payload=volume_contract.model_dump(mode="json"), **common,
    )
    chapter_contract = ChapterContract(
        contract_id="chapter_001", parent_volume_contract_id="volume_001",
        chapter_ordinal=1, chapter_plan=chapter_plan(), scene_slots=(scene_slot(),),
    )
    chapter = _artifact(
        repo, run, artifact_type="pnca.chapter.contract",
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
        contract_id="scene_contract_001", slot_id="scene_001",
        frontier_binding=binding, canon_effect="none",
        writer_view=writer_view(),
    )
    scene = _artifact(
        repo, run, artifact_type="pnca.scene.contract",
        logical_key="pnca.scene.contract.series_001.001.001.scene_001",
        payload=scene_contract.model_dump(mode="json"),
        input_artifact_ids=(chapter.artifact_id, root.artifact_id),
        canon_lineage_root_digest=seed.manifest.content_digest,
        input_canon_frontier_digest=root.manifest.content_digest,
    )
    accepted = repo.create_selection_snapshot(
        slug=slug,
        slots={
            "canon.seed": seed.artifact_id,
            "canon.frontier": root.artifact_id,
            "pnca.volume.contract.series_001.001": volume.artifact_id,
            "pnca.chapter.contract.series_001.001.001": chapter.artifact_id,
            "pnca.scene.contract.series_001.001.001.scene_001": scene.artifact_id,
        },
        reason="accepted bundle",
    )
    assert accepted.slots["pnca.scene.contract.series_001.001.001.scene_001"] == scene.artifact_id

    workflow = PNCAWorkflow(repository=repo, contract_author=object())
    if any(issue["severity"] == "blocker" for issue in audit_issues):
        with pytest.raises(RuntimeContractError, match="unresolved non-waivable audit issues"):
            workflow.write_volume(slug=slug, run=run, volume=1, executor=FakeExecutor(repo, audit_issues=audit_issues))
        assert "pnca.design_bundle.series_001.001" not in repo.load_snapshot(slug, repo.current_snapshot_id(slug)).slots
        return

    bundle = workflow.write_volume(slug=slug, run=run, volume=1, executor=FakeExecutor(repo, audit_issues=audit_issues))
    assert bundle.bundle_id == "series_001.volume.001"
    assert len(bundle.slots) == 1
    slot = bundle.slots[0]
    assert slot.scene_slot_id == "scene_001"
    assert slot.scene_contract_artifact_id == scene.artifact_id
    assert slot.draft_artifact_id
    assert slot.draft_assessment_artifact_id
    disposition = repo.read_payload(repo.verify_artifact(slot.quality_disposition_artifact_id))
    assert disposition["status"] == ("deferred" if audit_issues else "clean")
    assert len(disposition["findings"]) == len(audit_issues)
    frozen = workflow.load_selected_bundle(slug=slug, volume=1)
    assert frozen == bundle
    frozen_snapshot = repo.load_snapshot(slug, repo.current_snapshot_id(slug))
    bundle_artifact_id = frozen_snapshot.slots["pnca.design_bundle.series_001.001"]
    assert repo.verify_artifact(bundle_artifact_id).manifest.artifact_type == "pnca.design_bundle"

    exporter = PNCAExporter(repository=repo)
    manuscript = exporter.export(run=run, bundle=bundle, format="markdown")
    assert manuscript.artifact.artifact_id
    assert "シーンの本文" in manuscript.content
