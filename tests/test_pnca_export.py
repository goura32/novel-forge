"""Strict PNCA DesignBundle export tests."""

from __future__ import annotations

import pytest

from novel_forge.pnca.contracts import (
    BundleSlotRecord,
    DesignBundle,
    DraftAudit,
    QualityDisposition,
    QualityDispositionFinding,
)
from novel_forge.pnca.export import PNCAExporter, _validate_audit_disposition
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



def test_export_rejects_clean_hidden_quality_issue_and_mismatched_deferred_finding() -> None:
    audit = DraftAudit.model_validate(
        {
            "issues": [
                {
                    "severity": "major",
                    "constraint_kind": "quality",
                    "writer_view_field": "presentation_constraints",
                    "draft_quote": "リナは立ち止まった。",
                    "detail": "情景描写が薄い",
                }
            ]
        }
    )
    clean = QualityDisposition(
        scope_id="series.volume.scene",
        phase="write",
        subject_artifact_id="draft_001",
        review_artifact_ids=("audit_001",),
        status="clean",
    )
    with pytest.raises(RuntimeContractError, match="clean quality disposition"):
        _validate_audit_disposition(audit=audit, disposition=clean, assessment_id="audit_001")

    mismatched = QualityDisposition(
        scope_id="series.volume.scene",
        phase="write",
        subject_artifact_id="draft_001",
        review_artifact_ids=("audit_001",),
        status="deferred",
        findings=(
            QualityDispositionFinding(
                review_artifact_id="audit_001",
                issue_index=0,
                severity="major",
                constraint_kind="quality",
                writer_view_field="presentation_constraints",
                draft_quote="リナは立ち止まった。",
                detail="別の説明",
            ),
        ),
    )
    with pytest.raises(RuntimeContractError, match="does not match"):
        _validate_audit_disposition(audit=audit, disposition=mismatched, assessment_id="audit_001")


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
    disposition = _artifact(
        repo,
        run,
        artifact_type="pnca.quality_disposition",
        logical_key="pnca.quality_disposition.s1",
        payload={
            "scope_id": "series_001.volume.001.scene_001",
            "phase": "write",
            "subject_artifact_id": draft.artifact_id,
            "review_artifact_ids": [assessment.artifact_id],
            "status": "clean",
            "findings": [],
        },
        input_artifact_ids=(contract.artifact_id, view.artifact_id, draft.artifact_id, assessment.artifact_id),
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
                quality_disposition_artifact_id=disposition.artifact_id,
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
        disposition.artifact_id,
        frontier.artifact_id,
    }


@pytest.mark.parametrize(
    ("severity", "constraint_kind"),
    (("blocker", "required_beat"), ("major", "end_constraint")),
)
def test_export_rejects_schema_valid_nonwaivable_audit_even_with_clean_disposition(
    tmp_path, severity: str, constraint_kind: str
) -> None:
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
        payload={"content": "短い", "coverage": {"evidence": []}},
        input_artifact_ids=(view.artifact_id,),
    )
    assessment = _artifact(
        repo,
        run,
        artifact_type="pnca.draft_audit",
        logical_key="pnca.draft_audit.s1",
        payload={
            "issues": [
                {
                    "severity": severity,
                    "constraint_kind": constraint_kind,
                    "writer_view_field": "required_beats",
                    "draft_quote": "短い",
                    "detail": "契約上の残件",
                }
            ]
        },
        input_artifact_ids=(contract.artifact_id, view.artifact_id, draft.artifact_id),
    )
    disposition = _artifact(
        repo,
        run,
        artifact_type="pnca.quality_disposition",
        logical_key="pnca.quality_disposition.s1",
        payload={
            "scope_id": "series_001.volume.001.scene_001",
            "phase": "write",
            "subject_artifact_id": draft.artifact_id,
            "review_artifact_ids": [assessment.artifact_id],
            "status": "clean",
            "findings": [],
        },
        input_artifact_ids=(contract.artifact_id, view.artifact_id, draft.artifact_id, assessment.artifact_id),
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
                quality_disposition_artifact_id=disposition.artifact_id,
                output_frontier_artifact_id=frontier.artifact_id,
            ),
        ),
    )

    with pytest.raises(RuntimeContractError, match="non-waivable"):
        PNCAExporter(repo).export(run=run, bundle=bundle)
