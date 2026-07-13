"""Bounded immutable PNCA candidate and raw-audit lifecycle records."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from novel_forge.pnca.contracts import CandidatePlan, CandidatePolicy


class CandidateRecord(BaseModel):
    """One immutable fresh or revision candidate."""

    candidate_id: str = Field(min_length=1)
    content_digest: str = Field(min_length=1)
    origin: Literal["fresh", "revision"]
    parent_candidate_id: str | None = None

    @model_validator(mode="after")
    def _revision_has_parent_and_fresh_has_none(self) -> CandidateRecord:
        if self.origin == "revision" and not self.parent_candidate_id:
            raise ValueError("revision candidate requires parent_candidate_id")
        if self.origin == "fresh" and self.parent_candidate_id is not None:
            raise ValueError("fresh candidate must not name parent_candidate_id")
        return self


class RawAuditArtifact(BaseModel):
    """A completed or failed raw audit; failure is evidence, never omission."""

    candidate_id: str = Field(min_length=1)
    candidate_digest: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    status: Literal["completed", "failed"]
    failure_code: str | None = None

    @model_validator(mode="after")
    def _failure_has_explicit_failure_artifact_data(self) -> RawAuditArtifact:
        if self.status == "failed" and not self.failure_code:
            raise ValueError("failed RawAuditArtifact requires failure_code")
        if self.status == "completed" and self.failure_code is not None:
            raise ValueError("completed RawAuditArtifact must not have failure_code")
        return self


class CandidateBatch(BaseModel):
    """A complete, bounded candidate/audit set eligible for later synthesis."""

    policy: CandidatePolicy
    plan: CandidatePlan
    candidates: tuple[CandidateRecord, ...]
    audits: tuple[RawAuditArtifact, ...]

    @model_validator(mode="after")
    def _candidate_and_audit_topology_is_complete(self) -> CandidateBatch:
        if self.plan.policy_id != self.policy.policy_id:
            raise ValueError("CandidatePlan policy_id must equal CandidatePolicy policy_id")
        if self.plan.max_total_candidates != self.policy.max_total_candidates:
            raise ValueError("CandidatePlan cap must equal CandidatePolicy max_total_candidates")
        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        if tuple(candidate_ids) != self.plan.candidate_ids:
            raise ValueError("CandidateBatch candidates must match pinned CandidatePlan order")
        if len(candidate_ids) > self.policy.max_total_candidates:
            raise ValueError("CandidateBatch exceeds max_total_candidates")
        fresh = sum(candidate.origin == "fresh" for candidate in self.candidates)
        revision = sum(candidate.origin == "revision" for candidate in self.candidates)
        if fresh > self.policy.max_fresh_candidates:
            raise ValueError("CandidateBatch exceeds max_fresh_candidates")
        if revision > self.policy.max_revision_candidates:
            raise ValueError("CandidateBatch exceeds max_revision_candidates")
        digest_by_id = {candidate.candidate_id: candidate.content_digest for candidate in self.candidates}
        audits_by_candidate: dict[str, list[RawAuditArtifact]] = {key: [] for key in candidate_ids}
        for audit in self.audits:
            if audit.candidate_id not in digest_by_id:
                raise ValueError("RawAuditArtifact names an unplanned candidate")
            if audit.candidate_digest != digest_by_id[audit.candidate_id]:
                raise ValueError("RawAuditArtifact candidate digest does not match candidate")
            audits_by_candidate[audit.candidate_id].append(audit)
        for candidate_id, records in audits_by_candidate.items():
            if len(records) != self.policy.audits_per_candidate:
                raise ValueError(
                    f"candidate {candidate_id} requires exactly {self.policy.audits_per_candidate} raw audits"
                )
            profile_ids = [record.profile_id for record in records]
            if len(profile_ids) != len(set(profile_ids)):
                raise ValueError("raw audit profiles must be distinct per candidate")
        return self
