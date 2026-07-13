"""RED tests for PNCA TaskSpec registry and bounded candidate/audit batches."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from novel_forge.pnca.candidates import CandidateBatch, CandidateRecord, RawAuditArtifact
from novel_forge.pnca.contracts import CandidatePlan, CandidatePolicy
from novel_forge.pnca.registry import (
    ArtifactSpec,
    InputBinding,
    PNCATaskExecutor,
    PNCATaskRegistry,
    TaskSpec,
)


def _policy() -> CandidatePolicy:
    return CandidatePolicy(
        policy_id="policy_scene",
        max_total_candidates=2,
        max_fresh_candidates=1,
        max_revision_candidates=1,
        audits_per_candidate=3,
        max_input_tokens=4096,
        worst_case_candidate_input_tokens=2048,
        worst_case_selection_input_tokens=4096,
    )


def _registry() -> PNCATaskRegistry:
    return PNCATaskRegistry(
        specs=(
            TaskSpec(
                task_id="pnca.scene.contract.generate",
                task_kind="authoring",
                input_bindings=(
                    InputBinding(role="parent.requirement_ledger", variable="parent_ledger"),
                    InputBinding(role="scene.transition_packet", variable="transition_packet"),
                ),
                output=ArtifactSpec(
                    role="scene.contract.candidate",
                    artifact_type="pnca.scene.contract",
                    logical_key_template="pnca.scene.contract.{scene_slot_id}.{candidate_id}",
                ),
                prompt_digest="sha256:prompt",
                schema_digest="sha256:schema",
                model_profile="qwen3.6:35b-a3b-mtp-q4_K_M",
                max_input_bytes=256,
                max_output_bytes=512,
                idempotency_scope="scene_slot",
            ),
        )
    )


def test_registry_builds_only_declared_prompt_variables_with_pinned_resource_limits() -> None:
    registry = _registry()

    projection = registry.build_projection(
        task_id="pnca.scene.contract.generate",
        artifacts={
            "parent.requirement_ledger": {"requirements": ["req_001"]},
            "scene.transition_packet": {"frontier": "art_frontier"},
        },
    )

    assert set(projection) == {"parent_ledger", "transition_packet"}
    assert projection["parent_ledger"] == {"requirements": ["req_001"]}


def test_registry_rejects_undeclared_artifact_role_before_any_provider_call() -> None:
    registry = _registry()

    with pytest.raises(ValueError, match="undeclared artifact roles"):
        registry.build_projection(
            task_id="pnca.scene.contract.generate",
            artifacts={
                "parent.requirement_ledger": {},
                "scene.transition_packet": {},
                "summary": {"untrusted": True},
            },
        )


def test_registry_rejects_input_projection_over_its_pinned_byte_ceiling() -> None:
    registry = _registry()

    with pytest.raises(ValueError, match="max_input_bytes"):
        registry.build_projection(
            task_id="pnca.scene.contract.generate",
            artifacts={
                "parent.requirement_ledger": {"payload": "x" * 300},
                "scene.transition_packet": {},
            },
        )


def test_registry_rejects_duplicate_prompt_variable_bindings() -> None:
    with pytest.raises(ValidationError, match="variable names"):
        TaskSpec(
            task_id="invalid",
            task_kind="audit",
            input_bindings=(
                InputBinding(role="a", variable="same"),
                InputBinding(role="b", variable="same"),
            ),
            output=ArtifactSpec(role="audit", artifact_type="pnca.audit", logical_key_template="audit"),
            prompt_digest="sha256:prompt",
            schema_digest="sha256:schema",
            model_profile="model",
            max_input_bytes=1,
            max_output_bytes=1,
            idempotency_scope="scene_slot",
        )


def test_candidate_batch_requires_complete_raw_audit_evidence_for_every_candidate() -> None:
    policy = _policy()
    plan = CandidatePlan(
        plan_id="plan_scene",
        policy_id=policy.policy_id,
        candidate_ids=("cand_fresh", "cand_revision"),
        max_total_candidates=policy.max_total_candidates,
    )
    candidates = (
        CandidateRecord(candidate_id="cand_fresh", content_digest="sha256:fresh", origin="fresh"),
        CandidateRecord(
            candidate_id="cand_revision",
            content_digest="sha256:revision",
            origin="revision",
            parent_candidate_id="cand_fresh",
        ),
    )
    incomplete_audits = tuple(
        RawAuditArtifact(
            candidate_id=candidate.candidate_id,
            candidate_digest=candidate.content_digest,
            profile_id=profile,
            artifact_id=f"art_{candidate.candidate_id}_{profile}",
            status="completed",
        )
        for candidate in candidates
        for profile in ("structural", "canon")
    )

    with pytest.raises(ValidationError, match="exactly 3 raw audits"):
        CandidateBatch(
            policy=policy,
            plan=plan,
            candidates=candidates,
            audits=incomplete_audits,
        )


def test_candidate_batch_retains_failure_artifacts_instead_of_omitting_them() -> None:
    policy = _policy()
    plan = CandidatePlan(
        plan_id="plan_scene",
        policy_id=policy.policy_id,
        candidate_ids=("cand_fresh",),
        max_total_candidates=policy.max_total_candidates,
    )
    candidate = CandidateRecord(candidate_id="cand_fresh", content_digest="sha256:fresh", origin="fresh")
    audits = (
        RawAuditArtifact(
            candidate_id=candidate.candidate_id,
            candidate_digest=candidate.content_digest,
            profile_id="structural",
            artifact_id="art_audit_1",
            status="completed",
        ),
        RawAuditArtifact(
            candidate_id=candidate.candidate_id,
            candidate_digest=candidate.content_digest,
            profile_id="canon",
            artifact_id="art_audit_2",
            status="failed",
            failure_code="timeout",
        ),
        RawAuditArtifact(
            candidate_id=candidate.candidate_id,
            candidate_digest=candidate.content_digest,
            profile_id="writer_view",
            artifact_id="art_audit_3",
            status="completed",
        ),
    )

    batch = CandidateBatch(policy=policy, plan=plan, candidates=(candidate,), audits=audits)

    assert [audit.status for audit in batch.audits] == ["completed", "failed", "completed"]


def test_executor_uses_registry_projection_and_blocks_oversized_output() -> None:
    captured: list[tuple[str, dict[str, object], str]] = []

    def provider(task_id: str, variables: dict[str, object], key: str) -> object:
        captured.append((task_id, variables, key))
        return {"contract": "ok"}

    executor = PNCATaskExecutor(registry=_registry(), provider=provider)
    result = executor.execute(
        task_id="pnca.scene.contract.generate",
        scope_id="scene_001",
        artifacts={
            "parent.requirement_ledger": {"requirements": []},
            "scene.transition_packet": {"frontier": "art_root"},
        },
        input_artifact_ids=("art_ledger", "art_transition"),
    )

    assert result == {"contract": "ok"}
    assert captured[0][0] == "pnca.scene.contract.generate"
    assert set(captured[0][1]) == {"parent_ledger", "transition_packet"}
    assert captured[0][2].startswith("pnca:scene_slot:scene_001:")

    oversized = PNCATaskExecutor(registry=_registry(), provider=lambda *_: {"text": "x" * 600})
    with pytest.raises(ValueError, match="max_output_bytes"):
        oversized.execute(
            task_id="pnca.scene.contract.generate",
            scope_id="scene_001",
            artifacts={"parent.requirement_ledger": {}, "scene.transition_packet": {}},
            input_artifact_ids=("art_ledger", "art_transition"),
        )
