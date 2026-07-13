"""Strict PNCA DesignBundle export tests."""

from __future__ import annotations

import pytest

from novel_forge.pnca.contracts import BundleSlotRecord, DesignBundle
from novel_forge.pnca.export import PNCAExporter
from novel_forge.runtime import RunRepository, RuntimeContractError


def _artifact(repo: RunRepository, run, *, artifact_type: str, logical_key: str, payload, **kwargs):
    attempt = repo.start_attempt(run, task_id="pnca.test", phase="pnca", reason="test")
    return repo.commit_artifact(
        attempt,
        artifact_type=artifact_type,
        logical_key=logical_key,
        payload=payload,
        payload_name=f"{logical_key.replace('.', '_')}.json",
        **kwargs,
    )


def test_strict_export_uses_only_frozen_bundle_records(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)
    seed = _artifact(repo, run, artifact_type="canon.seed", logical_key="canon.seed", payload={"seed": True})
    frontier = _artifact(
        repo,
        run,
        artifact_type="canon.event_set",
        logical_key="canon.frontier.root",
        payload={"events": []},
        canon_lineage_root_digest=seed.manifest.content_digest,
    )
    contract = _artifact(repo, run, artifact_type="pnca.scene.contract", logical_key="pnca.scene.contract.s1", payload={})
    view = _artifact(
        repo,
        run,
        artifact_type="pnca.writer_view",
        logical_key="pnca.writer_view.s1",
        payload={"start_context": {}},
        input_artifact_ids=(contract.artifact_id,),
        metadata={"scene_contract_digest": contract.manifest.content_digest},
    )
    draft = _artifact(
        repo,
        run,
        artifact_type="pnca.scene_draft",
        logical_key="pnca.scene_draft.s1",
        payload={"content": "リナは塔へ向かった。", "coverage": {"evidence": []}},
        input_artifact_ids=(view.artifact_id,),
    )
    assessment = _artifact(
        repo,
        run,
        artifact_type="pnca.draft_audit",
        logical_key="pnca.draft_audit.s1",
        payload={"issues": []},
        input_artifact_ids=(contract.artifact_id, view.artifact_id, draft.artifact_id),
    )
    bundle = DesignBundle(
        bundle_id="bundle_001",
        slots=(
            BundleSlotRecord(
                volume_ordinal=1,
                chapter_ordinal=1,
                scene_ordinal=1,
                scene_slot_id="s1",
                scene_contract_artifact_id=contract.artifact_id,
                writer_view_artifact_id=view.artifact_id,
                draft_artifact_id=draft.artifact_id,
                draft_assessment_artifact_id=assessment.artifact_id,
                output_frontier_artifact_id=frontier.artifact_id,
            ),
        ),
    )

    exported = PNCAExporter(repo).export(run=run, bundle=bundle, format="markdown")

    assert exported.content == "# 第1巻\n\n## 第1章\n\n### シーン 1\n\nリナは塔へ向かった。\n"
    assert repo.read_payload(exported.artifact) == exported.content
    assert exported.artifact.manifest.metadata["bundle_id"] == "bundle_001"
    assert set(exported.artifact.manifest.input_artifact_ids) == {
        contract.artifact_id,
        view.artifact_id,
        draft.artifact_id,
        assessment.artifact_id,
        frontier.artifact_id,
    }


def test_export_rejects_blocker_audit_and_missing_output_frontier(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)
    seed = _artifact(repo, run, artifact_type="canon.seed", logical_key="canon.seed", payload={"seed": True})
    frontier = _artifact(
        repo,
        run,
        artifact_type="canon.event_set",
        logical_key="canon.frontier.root",
        payload={"events": []},
        canon_lineage_root_digest=seed.manifest.content_digest,
    )
    contract = _artifact(repo, run, artifact_type="pnca.scene.contract", logical_key="pnca.scene.contract.s1", payload={})
    view = _artifact(
        repo,
        run,
        artifact_type="pnca.writer_view",
        logical_key="pnca.writer_view.s1",
        payload={"start_context": {}},
        input_artifact_ids=(contract.artifact_id,),
        metadata={"scene_contract_digest": contract.manifest.content_digest},
    )
    draft = _artifact(
        repo,
        run,
        artifact_type="pnca.scene_draft",
        logical_key="pnca.scene_draft.s1",
        payload={"content": "短い"},
        input_artifact_ids=(view.artifact_id,),
    )
    assessment = _artifact(
        repo,
        run,
        artifact_type="pnca.draft_audit",
        logical_key="pnca.draft_audit.s1",
        payload={"issues": [{"severity": "blocker", "detail": "本文長不足"}]},
        input_artifact_ids=(contract.artifact_id, view.artifact_id, draft.artifact_id),
    )
    bundle = DesignBundle(
        bundle_id="bundle_001",
        slots=(
            BundleSlotRecord(
                volume_ordinal=1,
                chapter_ordinal=1,
                scene_ordinal=1,
                scene_slot_id="s1",
                scene_contract_artifact_id=contract.artifact_id,
                writer_view_artifact_id=view.artifact_id,
                draft_artifact_id=draft.artifact_id,
                draft_assessment_artifact_id=assessment.artifact_id,
                output_frontier_artifact_id=frontier.artifact_id,
            ),
        ),
    )

    with pytest.raises(RuntimeContractError, match="blocker"):
        PNCAExporter(repo).export(run=run, bundle=bundle)
