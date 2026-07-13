"""Progressive Narrative Contract Architecture structural records.

These records deliberately describe only immutable identity, topology, and typed
state-transition boundaries.  Natural-language adequacy is represented by audit
artifacts elsewhere and is never accepted here as a deterministic fact.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RequirementCardinality = Literal["exactly_once", "one_or_more", "preserve_until"]
RequirementDispositionKind = Literal["implemented", "preserved", "deferred"]
CanonEffect = Literal["none", "mutates"]


class FrontierBinding(BaseModel):
    """Exact immutable Canon frontier read by a Canon-consuming contract."""

    input_snapshot_id: str = Field(min_length=1)
    frontier_artifact_id: str = Field(min_length=1)
    frontier_digest: str = Field(min_length=1)
    lineage_root_digest: str = Field(min_length=1)


class RequirementEntry(BaseModel):
    """A parent-owned structural requirement and its permitted lifecycle."""

    requirement_id: str = Field(min_length=1)
    owner_scope: Literal["series", "volume", "chapter", "scene"]
    cardinality: RequirementCardinality
    allowed_next_owner: tuple[Literal["volume", "chapter", "scene"], ...] = ()
    defer_target_slot_id: str | None = None

    @model_validator(mode="after")
    def _defer_target_requires_descendant_owner(self) -> RequirementEntry:
        if self.defer_target_slot_id is not None and "scene" not in self.allowed_next_owner:
            raise ValueError("defer_target_slot_id requires scene in allowed_next_owner")
        return self


class ParentRequirementLedger(BaseModel):
    """Accepted parent requirements, created before child candidate generation."""

    owner_contract_id: str = Field(min_length=1)
    requirements: tuple[RequirementEntry, ...]

    @model_validator(mode="after")
    def _require_unique_ids(self) -> ParentRequirementLedger:
        ids = [item.requirement_id for item in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("ParentRequirementLedger requirement_id values must be unique")
        return self


class RequirementDisposition(BaseModel):
    """One child's declared handling of one parent requirement ID."""

    requirement_id: str = Field(min_length=1)
    disposition: RequirementDispositionKind
    defer_target_slot_id: str | None = None

    @model_validator(mode="after")
    def _deferred_target_is_disjoint(self) -> RequirementDisposition:
        if self.disposition == "deferred" and not self.defer_target_slot_id:
            raise ValueError("deferred disposition requires defer_target_slot_id")
        if self.disposition != "deferred" and self.defer_target_slot_id is not None:
            raise ValueError("only deferred disposition may name defer_target_slot_id")
        return self


class AdmissionAllowance(BaseModel):
    """A volume-authorized bounded creation allowance for one entity kind."""

    allowance_id: str = Field(min_length=1)
    kind: Literal["character", "location", "artifact", "organization"]
    max_count: int = Field(ge=1)


class AdmissionConsumption(BaseModel):
    """One scene's immutable use of an approved supporting-entity allowance."""

    allowance_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    kind: Literal["character", "location", "artifact", "organization"]


class SceneSlot(BaseModel):
    """One ordered placement allocated by an accepted Chapter Contract."""

    slot_id: str = Field(min_length=1)
    ordinal: int = Field(ge=1)
    allowed_admission_allowance_ids: tuple[str, ...] = ()


class SceneBeat(BaseModel):
    """One ordered, POV-observable beat that a scene prose draft must realize."""

    description: str = Field(min_length=1)


class WriterView(BaseModel):
    """The only authoritative input surface allowed to the prose writer."""

    model_config = ConfigDict(extra="forbid")

    start_context: dict[str, Any] = Field(default_factory=dict)
    narrative_contract: dict[str, Any] = Field(default_factory=dict)
    end_constraints: dict[str, Any] = Field(default_factory=dict)
    presentation_constraints: dict[str, Any] = Field(default_factory=dict)
    required_beats: tuple[SceneBeat | str, ...] = ()


class SceneContract(BaseModel):
    """An executable scene authority bounded by one pinned SceneSlot."""

    contract_id: str = Field(min_length=1)
    slot_id: str = Field(min_length=1)
    frontier_binding: FrontierBinding
    canon_effect: CanonEffect
    canon_patch: dict[str, Any] | None = None
    writer_view: WriterView = Field(default_factory=WriterView)
    requirement_dispositions: tuple[RequirementDisposition, ...] = ()
    admission_consumptions: tuple[AdmissionConsumption, ...] = ()

    @model_validator(mode="after")
    def _canon_effect_is_disjoint(self) -> SceneContract:
        if self.canon_effect == "none" and self.canon_patch is not None:
            raise ValueError("canon_effect none must not include canon_patch")
        if self.canon_effect == "mutates" and not self.canon_patch:
            raise ValueError("canon_effect mutates requires a non-empty canon_patch")
        return self


class SceneContractProposal(BaseModel):
    """Provider output before repository injects exact frontier provenance."""

    contract_id: str = Field(min_length=1)
    slot_id: str = Field(min_length=1)
    canon_effect: CanonEffect
    canon_patch: dict[str, Any] | None = None
    writer_view: WriterView = Field(default_factory=WriterView)
    requirement_dispositions: tuple[RequirementDisposition, ...] = ()
    admission_consumptions: tuple[AdmissionConsumption, ...] = ()

    @model_validator(mode="after")
    def _canon_effect_is_disjoint(self) -> SceneContractProposal:
        if self.canon_effect == "none" and self.canon_patch is not None:
            raise ValueError("canon_effect none must not include canon_patch")
        if self.canon_effect == "mutates" and not self.canon_patch:
            raise ValueError("canon_effect mutates requires a non-empty canon_patch")
        return self


class VolumePurpose(BaseModel):
    """One Series-owned one-line purpose for an ordered Volume."""

    ordinal: int = Field(ge=1)
    purpose: str = Field(min_length=1)


class SeriesContractProposal(BaseModel):
    """Provider output before repository-created Canon artifacts are pinned."""

    contract_id: str = Field(min_length=1, pattern=r"^[a-z0-9_]{1,40}$")
    canon_seed: dict[str, Any] = Field(min_length=1)
    volume_purposes: tuple[VolumePurpose, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _volume_purposes_are_ordered(self) -> SeriesContractProposal:
        ordinals = [item.ordinal for item in self.volume_purposes]
        if ordinals != sorted(ordinals) or len(ordinals) != len(set(ordinals)):
            raise ValueError("SeriesContractProposal volume purposes must have unique increasing ordinals")
        return self


class SeriesContract(BaseModel):
    """The root progressive contract and immutable Canon seed authority."""

    contract_id: str = Field(min_length=1)
    canon_seed_artifact_id: str = Field(min_length=1)
    root_frontier_artifact_id: str = Field(min_length=1)
    root_frontier_digest: str = Field(min_length=1)
    volume_purposes: tuple[VolumePurpose, ...] = Field(min_length=1)


class VolumeContract(BaseModel):
    """A bounded volume contract owned by exactly one SeriesContract."""

    contract_id: str = Field(min_length=1)
    parent_series_contract_id: str = Field(min_length=1)
    volume_ordinal: int = Field(ge=1)
    purpose: str = Field(default="", min_length=0)
    admission_allowances: tuple[AdmissionAllowance, ...] = ()

    @model_validator(mode="after")
    def _allowance_ids_are_unique(self) -> VolumeContract:
        ids = [item.allowance_id for item in self.admission_allowances]
        if len(ids) != len(set(ids)):
            raise ValueError("VolumeContract admission allowance IDs must be unique")
        return self


class ChapterContract(BaseModel):
    """A volume-bounded ordered topology of scene slots."""

    contract_id: str = Field(min_length=1)
    parent_volume_contract_id: str = Field(min_length=1)
    chapter_ordinal: int = Field(ge=1)
    volume_purpose: str = Field(default="", min_length=0)
    scene_slots: tuple[SceneSlot, ...]

    @model_validator(mode="after")
    def _slots_are_strictly_increasing(self) -> ChapterContract:
        ordinals = [slot.ordinal for slot in self.scene_slots]
        if ordinals != sorted(ordinals) or len(ordinals) != len(set(ordinals)):
            raise ValueError("ChapterContract SceneSlot ordinals must be strictly increasing")
        ids = [slot.slot_id for slot in self.scene_slots]
        if len(ids) != len(set(ids)):
            raise ValueError("ChapterContract SceneSlot IDs must be unique")
        return self


class CandidatePolicy(BaseModel):
    """A pinned bounded resource policy for one immutable candidate batch."""

    policy_id: str = Field(min_length=1)
    max_total_candidates: int = Field(ge=1)
    max_fresh_candidates: int = Field(ge=0)
    max_revision_candidates: int = Field(ge=0)
    audits_per_candidate: int = Field(ge=3, le=3)
    max_input_tokens: int = Field(ge=1)
    worst_case_candidate_input_tokens: int = Field(ge=1)
    worst_case_selection_input_tokens: int = Field(ge=1)

    @model_validator(mode="after")
    def _budget_is_closed_before_provider_call(self) -> CandidatePolicy:
        if self.max_fresh_candidates + self.max_revision_candidates > self.max_total_candidates:
            raise ValueError("fresh and revision candidate budgets exceed max_total_candidates")
        if self.worst_case_candidate_input_tokens > self.max_input_tokens:
            raise ValueError("worst_case_candidate_input_tokens exceeds max_input_tokens")
        if self.worst_case_selection_input_tokens > self.max_input_tokens:
            raise ValueError("worst_case_selection_input_tokens exceeds max_input_tokens")
        return self


class CandidatePlan(BaseModel):
    """The monotonic execution-credit plan pinned to CandidatePolicy."""

    plan_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    candidate_ids: tuple[str, ...]
    max_total_candidates: int = Field(ge=1)

    @model_validator(mode="after")
    def _candidate_ids_fit_policy_cap(self) -> CandidatePlan:
        if len(self.candidate_ids) > self.max_total_candidates:
            raise ValueError("CandidatePlan candidate_ids exceed max_total_candidates")
        if len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("CandidatePlan candidate_ids must be unique")
        return self


class OperationRecord(BaseModel):
    """Idempotent execution identity and its immutable terminal reference."""

    operation_key: str = Field(min_length=1)
    input_snapshot_id: str = Field(min_length=1)
    state: Literal["prepared", "executing", "artifacts_ready", "committed", "failed", "superseded"]
    acceptance_id: str | None = None

    @model_validator(mode="after")
    def _committed_requires_acceptance(self) -> OperationRecord:
        if self.state == "committed" and not self.acceptance_id:
            raise ValueError("committed OperationRecord requires acceptance_id")
        if self.state != "committed" and self.acceptance_id is not None:
            raise ValueError("only committed OperationRecord may reference acceptance_id")
        return self


class SceneStructuralAudit(BaseModel):
    """Provider-free structural audit evidence for one Scene Contract."""

    scene_contract_id: str = Field(min_length=1)
    checks: tuple[dict[str, Any], ...] = ()
    passed: bool = True


class SceneReviewSynthesis(BaseModel):
    """Deterministic synthesis of a structural audit batch."""

    scene_contract_id: str = Field(min_length=1)
    audit_batch_artifact_id: str = Field(min_length=1)
    observations: tuple[dict[str, Any], ...] = ()
    passed: bool = True


_REQUIRED_SCENE_ACCEPTANCE_ROLES = frozenset(
    {
        "scene.contract",
        "parent.requirement_ledger",
        "accepted.requirement_ledger",
        "audit.batch",
        "review.synthesis",
        "scene.slot_binding",
        "canon.frontier.output",
    }
)


class AcceptanceCommit(BaseModel):
    """The sole transition that makes a prepared PNCA scene state selected."""

    acceptance_id: str = Field(min_length=1)
    base_snapshot_id: str = Field(min_length=1)
    operation_key: str = Field(min_length=1)
    canon_effect: CanonEffect
    role_artifact_ids: dict[str, str]

    @model_validator(mode="after")
    def _contains_complete_scene_acceptance_group(self) -> AcceptanceCommit:
        missing = _REQUIRED_SCENE_ACCEPTANCE_ROLES - self.role_artifact_ids.keys()
        unexpected = self.role_artifact_ids.keys() - _REQUIRED_SCENE_ACCEPTANCE_ROLES
        if missing or unexpected:
            details: list[str] = []
            if missing:
                details.append(f"missing={sorted(missing)}")
            if unexpected:
                details.append(f"unexpected={sorted(unexpected)}")
            raise ValueError(f"AcceptanceCommit requires exactly the required role group ({', '.join(details)})")
        if any(not artifact_id for artifact_id in self.role_artifact_ids.values()):
            raise ValueError("AcceptanceCommit role artifact IDs must be non-empty")
        return self


_REQUIRED_SERIES_ACCEPTANCE_ROLES = frozenset(
    {"series.contract", "canon.seed", "canon.frontier.output"}
)


class SeriesAcceptanceCommit(BaseModel):
    """The sole root transition that makes the PNCA Series Contract visible."""

    acceptance_id: str = Field(min_length=1)
    operation_key: str = Field(min_length=1)
    role_artifact_ids: dict[str, str]

    @model_validator(mode="after")
    def _contains_complete_series_acceptance_group(self) -> SeriesAcceptanceCommit:
        missing = _REQUIRED_SERIES_ACCEPTANCE_ROLES - self.role_artifact_ids.keys()
        if missing:
            raise ValueError(f"SeriesAcceptanceCommit missing required role(s): {sorted(missing)}")
        if any(not artifact_id for artifact_id in self.role_artifact_ids.values()):
            raise ValueError("SeriesAcceptanceCommit role artifact IDs must be non-empty")
        return self


class VolumeAcceptanceCommit(BaseModel):
    """Atomic selection transition for one parent-pinned Volume Contract."""

    acceptance_id: str = Field(min_length=1)
    base_snapshot_id: str = Field(min_length=1)
    operation_key: str = Field(min_length=1)
    role_artifact_ids: dict[str, str]

    @model_validator(mode="after")
    def _contains_volume_contract(self) -> VolumeAcceptanceCommit:
        if set(self.role_artifact_ids) != {"volume.contract"}:
            raise ValueError("VolumeAcceptanceCommit requires exactly volume.contract")
        if not self.role_artifact_ids["volume.contract"]:
            raise ValueError("VolumeAcceptanceCommit volume.contract artifact ID must be non-empty")
        return self


class ChapterAcceptanceCommit(BaseModel):
    """Atomic selection transition for one Volume-pinned Chapter Contract."""

    acceptance_id: str = Field(min_length=1)
    base_snapshot_id: str = Field(min_length=1)
    operation_key: str = Field(min_length=1)
    role_artifact_ids: dict[str, str]

    @model_validator(mode="after")
    def _contains_chapter_contract(self) -> ChapterAcceptanceCommit:
        if set(self.role_artifact_ids) != {"chapter.contract"}:
            raise ValueError("ChapterAcceptanceCommit requires exactly chapter.contract")
        if not self.role_artifact_ids["chapter.contract"]:
            raise ValueError("ChapterAcceptanceCommit chapter.contract artifact ID must be non-empty")
        return self


class WriterViewReviewIssue(BaseModel):
    """One actionable pre-render finding against a scene WriterView."""

    field: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    description: str = Field(min_length=1)
    suggestion: str = Field(min_length=1)


class WriterViewReview(BaseModel):
    """A bounded review result that either accepts or requests a WriterView revision."""

    issues: tuple[WriterViewReviewIssue, ...]


class DraftObligationEvidence(BaseModel):
    """One exact prose quote proving a WriterView obligation was realized."""

    model_config = ConfigDict(extra="forbid")

    obligation: Literal["required_beat", "end_constraint"]
    beat_index: int | None = Field(default=None, ge=0)
    draft_quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def _indexes_only_required_beats(self) -> DraftObligationEvidence:
        if self.obligation == "required_beat" and self.beat_index is None:
            raise ValueError("required_beat evidence requires beat_index")
        if self.obligation == "end_constraint" and self.beat_index is not None:
            raise ValueError("end_constraint evidence must not have beat_index")
        return self


class DraftCoverage(BaseModel):
    """Writer-supplied, exact-quote evidence for every mandatory prose obligation."""

    model_config = ConfigDict(extra="forbid")

    evidence: tuple[DraftObligationEvidence, ...]


class DraftAuditIssue(BaseModel):
    """A grounded finding against one rendered scene."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["blocker", "major", "minor"]
    constraint_kind: Literal["required_beat", "end_constraint", "pov_fact", "language_contamination", "quality"]
    writer_view_field: str = Field(min_length=1)
    draft_quote: str = Field(min_length=1)
    detail: str = Field(min_length=1)

    @model_validator(mode="after")
    def _blockers_are_limited_to_hard_contract_failures(self) -> DraftAuditIssue:
        hard_kinds = {"required_beat", "end_constraint", "pov_fact", "language_contamination"}
        if self.severity == "blocker" and self.constraint_kind not in hard_kinds:
            raise ValueError("blocker severity is reserved for hard contract failures")
        return self


class DraftAudit(BaseModel):
    """An explicit audit result; an empty issue list is the only clean result."""

    model_config = ConfigDict(extra="forbid")

    issues: tuple[DraftAuditIssue, ...]


class BundleSlotRecord(BaseModel):
    """One fully pinned topology row consumed by writer and export."""

    volume_ordinal: int = Field(ge=1)
    chapter_ordinal: int = Field(ge=1)
    scene_ordinal: int = Field(ge=1)
    scene_slot_id: str = Field(min_length=1)
    scene_contract_artifact_id: str = Field(min_length=1)
    writer_view_artifact_id: str = Field(min_length=1)
    draft_artifact_id: str = Field(min_length=1)
    draft_assessment_artifact_id: str = Field(min_length=1)
    output_frontier_artifact_id: str = Field(min_length=1)


class DesignBundle(BaseModel):
    """Frozen ordered design/export topology without a mutable latest lookup."""

    bundle_id: str = Field(min_length=1)
    slots: tuple[BundleSlotRecord, ...]

    @model_validator(mode="after")
    def _slot_topology_is_unique_and_ordered(self) -> DesignBundle:
        keys = [
            (slot.volume_ordinal, slot.chapter_ordinal, slot.scene_ordinal)
            for slot in self.slots
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("DesignBundle topology keys must be unique")
        if keys != sorted(keys):
            raise ValueError("DesignBundle topology must be ordered")
        ids = [slot.scene_slot_id for slot in self.slots]
        if len(ids) != len(set(ids)):
            raise ValueError("DesignBundle scene_slot_id values must be unique")
        return self
