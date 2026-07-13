"""Deterministic PNCA structural validation.

No function here decides whether prose, causality, or a natural-language requirement
is semantically adequate.  It validates only IDs, declared topology, authority, and
bounded typed resource usage.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from novel_forge.pnca.contracts import (
    AdmissionAllowance,
    AdmissionConsumption,
    ParentRequirementLedger,
    SceneContract,
    SceneSlot,
    WriterView,
)


class PNCAStructuralError(ValueError):
    """A deterministic PNCA contract or topology failure."""


_WRITER_FORBIDDEN_KEYS = frozenset(
    {
        "artifact_id",
        "canon",
        "canon_event",
        "canon_patch",
        "canon_snapshot",
        "event_log",
        "stable_id",
        "summary",
    }
)


def validate_writer_view(view: WriterView) -> None:
    """Reject authority-bearing inputs from the prose-writer boundary."""

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in _WRITER_FORBIDDEN_KEYS:
                    raise PNCAStructuralError(f"forbidden writer input: {key}")
                walk(nested)
        elif isinstance(value, (tuple, list)):
            for nested in value:
                walk(nested)

    walk(view.model_dump())


def validate_scene_structure(
    *,
    contract: SceneContract,
    parent_ledger: ParentRequirementLedger,
    scene_slots: Iterable[SceneSlot],
    admission_allowances: Iterable[AdmissionAllowance],
    consumed_admissions: Iterable[AdmissionConsumption],
) -> None:
    """Validate one SceneContract against accepted parent structural authority."""

    validate_writer_view(contract.writer_view)
    slots = tuple(scene_slots)
    slot_by_id = {slot.slot_id: slot for slot in slots}
    if len(slot_by_id) != len(slots):
        raise PNCAStructuralError("duplicate SceneSlot slot_id")
    ordinals = [slot.ordinal for slot in slots]
    if len(ordinals) != len(set(ordinals)):
        raise PNCAStructuralError("duplicate SceneSlot ordinal")
    current_slot = slot_by_id.get(contract.slot_id)
    if current_slot is None:
        raise PNCAStructuralError(f"SceneContract slot is not allocated: {contract.slot_id}")

    requirements = {item.requirement_id: item for item in parent_ledger.requirements}
    disposition_ids = [item.requirement_id for item in contract.requirement_dispositions]
    duplicate = _first_duplicate(disposition_ids)
    if duplicate is not None:
        raise PNCAStructuralError(f"duplicate requirement disposition: {duplicate}")
    for disposition in contract.requirement_dispositions:
        requirement = requirements.get(disposition.requirement_id)
        if requirement is None:
            raise PNCAStructuralError(
                f"requirement disposition is not owned by parent ledger: {disposition.requirement_id}"
            )
        if disposition.disposition != "deferred":
            continue
        target_id = disposition.defer_target_slot_id
        assert target_id is not None  # guaranteed by RequirementDisposition model
        if requirement.defer_target_slot_id != target_id:
            raise PNCAStructuralError(
                f"deferred requirement target is not predeclared: {disposition.requirement_id}"
            )
        target = slot_by_id.get(target_id)
        if target is None or target.ordinal <= current_slot.ordinal:
            raise PNCAStructuralError(
                f"deferred requirement must name a later target slot: {disposition.requirement_id}"
            )

    _validate_admissions(
        contract=contract,
        current_slot=current_slot,
        allowances=tuple(admission_allowances),
        already_consumed=tuple(consumed_admissions),
    )


def _validate_admissions(
    *,
    contract: SceneContract,
    current_slot: SceneSlot,
    allowances: tuple[AdmissionAllowance, ...],
    already_consumed: tuple[AdmissionConsumption, ...],
) -> None:
    allowance_by_id = {allowance.allowance_id: allowance for allowance in allowances}
    if len(allowance_by_id) != len(allowances):
        raise PNCAStructuralError("duplicate AdmissionAllowance allowance_id")

    entity_ids = [item.entity_id for item in contract.admission_consumptions]
    duplicate = _first_duplicate(entity_ids)
    if duplicate is not None:
        raise PNCAStructuralError(f"duplicate supporting entity admission: {duplicate}")

    all_consumptions = (*already_consumed, *contract.admission_consumptions)
    count_by_allowance = Counter(item.allowance_id for item in all_consumptions)
    for consumption in contract.admission_consumptions:
        allowance = allowance_by_id.get(consumption.allowance_id)
        if allowance is None or consumption.allowance_id not in current_slot.allowed_admission_allowance_ids:
            raise PNCAStructuralError(
                f"supporting entity admission is not authorized: {consumption.allowance_id}"
            )
        if allowance.kind != consumption.kind:
            raise PNCAStructuralError(
                f"supporting entity admission kind mismatch: {consumption.allowance_id}"
            )
        if count_by_allowance[consumption.allowance_id] > allowance.max_count:
            raise PNCAStructuralError(
                f"supporting entity admission allowance is exhausted: {consumption.allowance_id}"
            )


def _first_duplicate(values: Iterable[str]) -> str | None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            return value
        seen.add(value)
    return None
