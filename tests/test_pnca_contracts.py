"""RED contracts for the PNCA structural foundation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from novel_forge.pnca.contracts import (
    AcceptanceCommit,
    AdmissionAllowance,
    AdmissionConsumption,
    BundleSlotRecord,
    CandidatePlan,
    CandidatePolicy,
    ChapterContract,
    DesignBundle,
    DraftAudit,
    FrontierBinding,
    OperationRecord,
    ParentRequirementLedger,
    QualityDisposition,
    QualityDispositionFinding,
    RequirementDisposition,
    RequirementEntry,
    SceneContract,
    SceneContractProposal,
    SceneSlot,
    SeriesContract,
    SeriesContractProposal,
    VolumeContract,
    VolumePurpose,
    WriterView,
)
from novel_forge.pnca.validation import (
    PNCAStructuralError,
    validate_scene_structure,
    validate_writer_view,
)


def _binding() -> FrontierBinding:
    return FrontierBinding(
        input_snapshot_id="sel_parent",
        frontier_artifact_id="art_frontier_parent",
        frontier_digest="sha256:frontier-parent",
        lineage_root_digest="sha256:seed",
    )


def _ledger() -> ParentRequirementLedger:
    return ParentRequirementLedger(
        owner_contract_id="chapter_001",
        requirements=(
            RequirementEntry(
                requirement_id="req_entry",
                owner_scope="chapter",
                cardinality="exactly_once",
            ),
            RequirementEntry(
                requirement_id="req_reveal",
                owner_scope="chapter",
                cardinality="preserve_until",
                allowed_next_owner=("scene",),
                defer_target_slot_id="scene_002",
            ),
        ),
    )


def _slots() -> tuple[SceneSlot, ...]:
    return (
        SceneSlot(slot_id="scene_001", ordinal=1, allowed_admission_allowance_ids=("allow_support",)),
        SceneSlot(slot_id="scene_002", ordinal=2),
    )


def test_series_proposal_rejects_seed_without_two_named_protagonists() -> None:
    with pytest.raises(ValidationError, match="protagonists"):
        SeriesContractProposal(
            contract_id="moon_flower",
            canon_seed={
                "series": {"title": "月影の花", "logline": "呪われた王子との政略結婚"},
                "world_state": {"curse": "月光で発作が起きる"},
            },
            volume_purposes=(VolumePurpose(ordinal=1, purpose="政略結婚を受け入れる"),),
        )


def test_scene_proposal_rejects_pov_character_alias_in_writer_view() -> None:
    with pytest.raises(ValidationError, match="canonical `pov`"):
        SceneContractProposal(
            contract_id="scene_001_proposal",
            canon_effect="none",
            writer_view=WriterView(
                start_context={"pov_character": "凛花"},
                narrative_contract={"goal": "朔夜の反応を観察する"},
                end_constraints={"pov_character": "凛花"},
                presentation_constraints={"pov_character": "凛花", "tone": "抑制的"},
                required_beats=("凛花が朔夜の指先の震えを見る",),
            ),
        )


def test_writer_view_exposes_required_observable_beats_to_the_writer() -> None:
    view = WriterView(
        start_context={"pov": "リナ"},
        narrative_contract={"goal": "鍵を探す"},
        end_constraints={"location": "塔"},
        presentation_constraints={"pov": "三人称"},
        required_beats=({"description": "リナが鍵穴に手を伸ばす"},),
    )

    assert view.model_dump()["narrative_contract"]["goal"] == "鍵を探す"
    assert view.required_beats[0].description == "リナが鍵穴に手を伸ばす"




def test_draft_audit_rejects_a_blocker_without_hard_contract_evidence() -> None:
    with pytest.raises(ValidationError, match="blocker"):
        DraftAudit.model_validate(
            {
                "issues": [
                    {
                        "severity": "blocker",
                        "constraint_kind": "quality",
                        "writer_view_field": "narrative_contract.purpose",
                        "draft_quote": "雪は静かに降っていた。",
                        "detail": "背景説明が不足している。",
                    }
                ]
            }
        )


def test_draft_audit_accepts_a_grounded_pov_blocker() -> None:
    audit = DraftAudit.model_validate(
        {
            "issues": [
                {
                    "severity": "blocker",
                    "constraint_kind": "pov_fact",
                    "writer_view_field": "presentation_constraints",
                    "draft_quote": "公爵は彼女を愛していた。",
                    "detail": "POV人物が知り得ない未発話の内面を断定している。",
                }
            ]
        }
    )
    assert audit.issues[0].severity == "blocker"


def test_quality_disposition_allows_only_quality_findings_to_be_deferred() -> None:
    disposition = QualityDisposition(
        scope_id="series_001.volume.001.scene_001",
        phase="write",
        subject_artifact_id="art_draft",
        review_artifact_ids=("art_audit",),
        status="deferred",
        findings=(
            QualityDispositionFinding(
                review_artifact_id="art_audit",
                issue_index=0,
                severity="minor",
                constraint_kind="quality",
                writer_view_field="narrative_contract.style",
                draft_quote="雪は静かに降っていた。",
                detail="語彙の反復。",
            ),
        ),
    )
    assert disposition.status == "deferred"


def test_quality_disposition_rejects_deferred_hard_contract_finding() -> None:
    with pytest.raises(ValidationError, match="quality"):
        QualityDisposition(
            scope_id="series_001.volume.001.scene_001",
            phase="write",
            subject_artifact_id="art_draft",
            review_artifact_ids=("art_audit",),
            status="deferred",
            findings=(
                QualityDispositionFinding(
                    review_artifact_id="art_audit",
                    issue_index=0,
                    severity="major",
                    constraint_kind="pov_fact",
                    writer_view_field="presentation_constraints.pov",
                    draft_quote="彼は恐れている。",
                    detail="他者の内面断定。",
                ),
            ),
        )


def test_writer_view_preserves_string_beats_when_provider_uses_compact_form() -> None:
    view = WriterView(required_beats=("リナが鍵穴に手を伸ばす",))

    assert view.required_beats == ("リナが鍵穴に手を伸ばす",)

    with pytest.raises(PNCAStructuralError, match="forbidden writer input"):
        validate_writer_view(
            view.model_copy(update={"start_context": {"canon": {"all": "facts"}}})
        )


def test_no_effect_scene_rejects_any_patch() -> None:
    with pytest.raises(ValidationError, match="canon_effect none"):
        SceneContract(
            contract_id="scene_contract_001",
            slot_id="scene_001",
            frontier_binding=_binding(),
            canon_effect="none",
            canon_patch={"characters": {"state_updates": [{"id": "char_001"}]}},
        )


def test_mutating_scene_requires_a_nonempty_patch() -> None:
    with pytest.raises(ValidationError, match="non-empty canon_patch"):
        SceneContract(
            contract_id="scene_contract_001",
            slot_id="scene_001",
            frontier_binding=_binding(),
            canon_effect="mutates",
            canon_patch={},
        )


def test_frontier_binding_rejects_blank_identity_fields() -> None:
    with pytest.raises(ValidationError, match="frontier_artifact_id"):
        FrontierBinding(
            input_snapshot_id="sel_parent",
            frontier_artifact_id="",
            frontier_digest="sha256:frontier-parent",
            lineage_root_digest="sha256:seed",
        )


def test_deferred_requirement_must_name_its_predeclared_later_slot() -> None:
    ledger = ParentRequirementLedger(
        owner_contract_id="chapter_001",
        requirements=(
            RequirementEntry(
                requirement_id="req_reveal",
                owner_scope="chapter",
                cardinality="preserve_until",
                allowed_next_owner=("scene",),
                defer_target_slot_id="scene_001",
            ),
        ),
    )
    contract = SceneContract(
        contract_id="scene_contract_001",
        slot_id="scene_001",
        frontier_binding=_binding(),
        canon_effect="none",
        requirement_dispositions=(
            RequirementDisposition(
                requirement_id="req_reveal",
                disposition="deferred",
                defer_target_slot_id="scene_001",
            ),
        ),
    )

    with pytest.raises(PNCAStructuralError, match="later target slot"):
        validate_scene_structure(
            contract=contract,
            parent_ledger=ledger,
            scene_slots=_slots(),
            admission_allowances=(),
            consumed_admissions=(),
        )


def test_scene_rejects_unapproved_supporting_entity_admission() -> None:
    contract = SceneContract(
        contract_id="scene_contract_001",
        slot_id="scene_001",
        frontier_binding=_binding(),
        canon_effect="none",
        admission_consumptions=(
            AdmissionConsumption(
                allowance_id="allow_unknown",
                entity_id="character_guest",
                kind="character",
            ),
        ),
    )

    with pytest.raises(PNCAStructuralError, match="not authorized"):
        validate_scene_structure(
            contract=contract,
            parent_ledger=_ledger(),
            scene_slots=_slots(),
            admission_allowances=(AdmissionAllowance(allowance_id="allow_support", kind="character", max_count=1),),
            consumed_admissions=(),
        )


def test_scene_rejects_duplicate_admission_consumption_across_selected_slots() -> None:
    allowance = AdmissionAllowance(allowance_id="allow_support", kind="character", max_count=1)
    prior = AdmissionConsumption(
        allowance_id="allow_support",
        entity_id="character_prior",
        kind="character",
    )
    contract = SceneContract(
        contract_id="scene_contract_001",
        slot_id="scene_001",
        frontier_binding=_binding(),
        canon_effect="none",
        admission_consumptions=(
            AdmissionConsumption(
                allowance_id="allow_support",
                entity_id="character_new",
                kind="character",
            ),
        ),
    )

    with pytest.raises(PNCAStructuralError, match="exhausted"):
        validate_scene_structure(
            contract=contract,
            parent_ledger=_ledger(),
            scene_slots=_slots(),
            admission_allowances=(allowance,),
            consumed_admissions=(prior,),
        )


def test_scene_rejects_duplicate_requirement_disposition() -> None:
    contract = SceneContract(
        contract_id="scene_contract_001",
        slot_id="scene_001",
        frontier_binding=_binding(),
        canon_effect="none",
        requirement_dispositions=(
            RequirementDisposition(requirement_id="req_entry", disposition="implemented"),
            RequirementDisposition(requirement_id="req_entry", disposition="preserved"),
        ),
    )

    with pytest.raises(PNCAStructuralError, match="duplicate requirement disposition"):
        validate_scene_structure(
            contract=contract,
            parent_ledger=_ledger(),
            scene_slots=_slots(),
            admission_allowances=(),
            consumed_admissions=(),
        )


def test_progressive_contracts_preserve_parent_identity_and_slot_topology() -> None:
    series = SeriesContract(
        contract_id="series_001",
        canon_seed_artifact_id="art_seed",
        root_frontier_artifact_id="art_frontier_root",
        root_frontier_digest="sha256:root",
        volume_purposes=(VolumePurpose(ordinal=1, purpose="導入"),),
    )
    volume = VolumeContract(
        contract_id="volume_001",
        parent_series_contract_id=series.contract_id,
        volume_ordinal=1,
    )

    with pytest.raises(ValidationError, match="strictly increasing"):
        ChapterContract(
            contract_id="chapter_001",
            parent_volume_contract_id=volume.contract_id,
            chapter_ordinal=1,
            scene_slots=(
                SceneSlot(slot_id="scene_002", ordinal=2),
                SceneSlot(slot_id="scene_001", ordinal=1),
            ),
        )


def test_candidate_plan_cannot_exceed_its_pinned_policy() -> None:
    policy = CandidatePolicy(
        policy_id="policy_scene",
        max_total_candidates=2,
        max_fresh_candidates=1,
        max_revision_candidates=1,
        audits_per_candidate=3,
        max_input_tokens=4096,
        worst_case_candidate_input_tokens=2048,
        worst_case_selection_input_tokens=4096,
    )

    with pytest.raises(ValidationError, match="max_total_candidates"):
        CandidatePlan(
            plan_id="plan_scene",
            policy_id=policy.policy_id,
            candidate_ids=("cand_001", "cand_002", "cand_003"),
            max_total_candidates=policy.max_total_candidates,
        )


def test_candidate_policy_rejects_unbounded_raw_audit_selection_input() -> None:
    with pytest.raises(ValidationError, match="worst_case_selection_input_tokens"):
        CandidatePolicy(
            policy_id="policy_scene",
            max_total_candidates=1,
            max_fresh_candidates=1,
            max_revision_candidates=0,
            audits_per_candidate=3,
            max_input_tokens=4096,
            worst_case_candidate_input_tokens=2048,
            worst_case_selection_input_tokens=4097,
        )


def test_operation_record_rejects_committed_state_without_acceptance_id() -> None:
    with pytest.raises(ValidationError, match="acceptance_id"):
        OperationRecord(
            operation_key="series:sel_parent:scene:contract",
            input_snapshot_id="sel_parent",
            state="committed",
        )


def test_acceptance_commit_requires_a_scene_frontier_evidence_group() -> None:
    with pytest.raises(ValidationError, match="required role"):
        AcceptanceCommit(
            acceptance_id="accept_scene_001",
            base_snapshot_id="sel_parent",
            operation_key="series:sel_parent:scene:contract",
            canon_effect="mutates",
            role_artifact_ids={"scene.contract": "art_scene"},
        )


def test_design_bundle_rejects_duplicate_or_nonsequential_slot_topology() -> None:
    duplicate = BundleSlotRecord(
        volume_ordinal=1,
        chapter_ordinal=1,
        scene_ordinal=1,
        scene_slot_id="scene_001",
        scene_contract_artifact_id="art_scene_001",
        writer_view_artifact_id="art_view_001",
        draft_artifact_id="art_draft_001",
        draft_assessment_artifact_id="art_assessment_001",
        quality_disposition_artifact_id="art_disposition_001",
        output_frontier_artifact_id="art_frontier_001",
    )
    with pytest.raises(ValidationError, match="unique"):
        DesignBundle(bundle_id="bundle_001", slots=(duplicate, duplicate))
