"""RED tests for the PNCA atomic acceptance repository boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from novel_forge.pnca.contracts import (
    AcceptanceCommit,
    FrontierBinding,
    SeriesAcceptanceCommit,
    VolumeAcceptanceCommit,
)
from novel_forge.runtime import RunRepository, RuntimeContractError


def _artifact(
    repo: RunRepository,
    run,
    *,
    artifact_type: str,
    logical_key: str,
    payload: object,
    **manifest_kwargs: object,
):
    attempt = repo.start_attempt(run, task_id="pnca.test", phase="pnca", reason="test")
    return repo.commit_artifact(
        attempt,
        artifact_type=artifact_type,
        logical_key=logical_key,
        payload=payload,
        payload_name=f"{logical_key.replace('.', '_')}.json",
        **manifest_kwargs,
    )


def _bootstrap(repo: RunRepository):
    run = repo.create_run(command="plan", model="fake", verbose=False)
    seed = _artifact(
        repo,
        run,
        artifact_type="canon.seed",
        logical_key="canon.seed",
        payload={"seed": True},
    )
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


def _prepared_scene_acceptance(repo: RunRepository):
    run, seed, root, base = _bootstrap(repo)
    common = {
        "canon_lineage_root_digest": seed.manifest.content_digest,
        "input_canon_frontier_digest": root.manifest.content_digest,
        "input_artifact_ids": (root.artifact_id,),
    }
    scene = _artifact(
        repo,
        run,
        artifact_type="pnca.scene.contract",
        logical_key="pnca.scene.contract.scene_001",
        payload={"scene": "scene_001"},
        **common,
    )
    parent_ledger = _artifact(
        repo,
        run,
        artifact_type="pnca.parent_requirement_ledger",
        logical_key="pnca.ledger.parent.scene_001",
        payload={"requirements": []},
        **common,
    )
    accepted_ledger = _artifact(
        repo,
        run,
        artifact_type="pnca.accepted_requirement_ledger",
        logical_key="pnca.ledger.accepted.scene_001",
        payload={"requirements": []},
        **common,
    )
    audits = _artifact(
        repo,
        run,
        artifact_type="pnca.audit.batch",
        logical_key="pnca.audit.batch.scene_001",
        payload={"audits": [{"index": 1}, {"index": 2}, {"index": 3}]},
        **common,
    )
    synthesis = _artifact(
        repo,
        run,
        artifact_type="pnca.review.synthesis",
        logical_key="pnca.review.synthesis.scene_001",
        payload={"observations": []},
        **common,
    )
    slot = _artifact(
        repo,
        run,
        artifact_type="pnca.scene.slot_binding",
        logical_key="pnca.scene.slot.scene_001",
        payload={"slot": "scene_001"},
        **common,
    )
    patch = _artifact(
        repo,
        run,
        artifact_type="canon.patch",
        logical_key="canon.patch.scene_001",
        payload={"patch": "typed"},
        **common,
    )
    output = _artifact(
        repo,
        run,
        artifact_type="canon.event_set",
        logical_key="canon.frontier.scene_001",
        payload={"events": [{"source": "scene_001"}]},
        canon_lineage_root_digest=seed.manifest.content_digest,
        input_canon_frontier_digest=root.manifest.content_digest,
        parent_frontier_artifact_id=root.artifact_id,
        parent_frontier_digest=root.manifest.content_digest,
        source_patch_artifact_ids=(patch.artifact_id,),
        metadata={
            "source_scene_contract_artifact_id": scene.artifact_id,
            "source_scene_contract_digest": scene.manifest.content_digest,
        },
    )
    roles = {
        "scene.contract": scene.artifact_id,
        "parent.requirement_ledger": parent_ledger.artifact_id,
        "accepted.requirement_ledger": accepted_ledger.artifact_id,
        "audit.batch": audits.artifact_id,
        "review.synthesis": synthesis.artifact_id,
        "scene.slot_binding": slot.artifact_id,
        "canon.frontier.output": output.artifact_id,
    }
    acceptance = AcceptanceCommit(
        acceptance_id="accept_scene_001",
        base_snapshot_id=base.selection_snapshot_id,
        operation_key="series:base:scene_001:accept",
        canon_effect="mutates",
        role_artifact_ids=roles,
    )
    binding = FrontierBinding(
        input_snapshot_id=base.selection_snapshot_id,
        frontier_artifact_id=root.artifact_id,
        frontier_digest=root.manifest.content_digest,
        lineage_root_digest=seed.manifest.content_digest,
    )
    return acceptance, binding, base, output


def test_acceptance_commit_publishes_all_prepared_roles_in_one_descendant_snapshot(
    tmp_path: Path,
) -> None:
    repo = RunRepository(tmp_path)
    acceptance, binding, base, output = _prepared_scene_acceptance(repo)

    snapshot = repo.commit_pnca_acceptance(
        slug="series",
        acceptance=acceptance,
        frontier_binding=binding,
    )

    assert snapshot.base_snapshot_id == base.selection_snapshot_id
    assert snapshot.slots["canon.frontier"] == output.artifact_id
    assert snapshot.slots["pnca.scene.contract.scene_001"] == acceptance.role_artifact_ids["scene.contract"]
    assert repo.load_snapshot("series", base.selection_snapshot_id).slots["canon.frontier"] == binding.frontier_artifact_id


def test_series_acceptance_atomically_bootstraps_the_pnca_root(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
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
    series = _artifact(
        repo,
        run,
        artifact_type="pnca.series.contract",
        logical_key="pnca.series.contract.series_001",
        payload={"contract_id": "series_001"},
    )
    acceptance = SeriesAcceptanceCommit(
        acceptance_id="accept_series_001",
        operation_key="series_001:root:accept",
        role_artifact_ids={
            "series.contract": series.artifact_id,
            "canon.seed": seed.artifact_id,
            "canon.frontier.output": root.artifact_id,
        },
    )

    snapshot = repo.commit_pnca_series_acceptance(slug="series_001", acceptance=acceptance)

    assert snapshot.base_snapshot_id is None
    assert snapshot.slots == {
        "canon.frontier": root.artifact_id,
        "canon.seed": seed.artifact_id,
        "pnca.series.contract.series_001": series.artifact_id,
    }
    assert repo.current_snapshot_id("series_001") == snapshot.selection_snapshot_id



def test_volume_acceptance_publishes_parent_pinned_volume_slot(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)
    seed = _artifact(repo, run, artifact_type="canon.seed", logical_key="canon.seed", payload={"seed": True})
    root = _artifact(repo, run, artifact_type="canon.event_set", logical_key="canon.frontier.root", payload={"events": []}, canon_lineage_root_digest=seed.manifest.content_digest)
    series = _artifact(repo, run, artifact_type="pnca.series.contract", logical_key="pnca.series.contract.series_001", payload={"contract_id": "series_001"})
    base = repo.commit_pnca_series_acceptance(slug="series_001", acceptance=SeriesAcceptanceCommit(acceptance_id="accept_series", operation_key="series_001:root:accept", role_artifact_ids={"series.contract": series.artifact_id, "canon.seed": seed.artifact_id, "canon.frontier.output": root.artifact_id}))
    design_run = repo.create_run(command="design", model="fake", verbose=False, input_snapshot_id=base.selection_snapshot_id)
    volume = _artifact(repo, design_run, artifact_type="pnca.volume.contract", logical_key="pnca.volume.contract.series_001.001", payload={"contract_id": "volume_001", "volume_ordinal": 1}, input_artifact_ids=(series.artifact_id,))

    snapshot = repo.commit_pnca_volume_acceptance(slug="series_001", acceptance=VolumeAcceptanceCommit(acceptance_id="accept_volume_001", base_snapshot_id=base.selection_snapshot_id, operation_key="series_001:volume:001:accept", role_artifact_ids={"volume.contract": volume.artifact_id}))

    assert snapshot.base_snapshot_id == base.selection_snapshot_id
    assert snapshot.slots["pnca.series.contract.series_001"] == series.artifact_id
    assert snapshot.slots["volume.contract.001"] == volume.artifact_id

def test_acceptance_rejects_frontier_digest_that_is_not_the_exact_base_snapshot_frontier(
    tmp_path: Path,
) -> None:
    repo = RunRepository(tmp_path)
    acceptance, binding, _base, _output = _prepared_scene_acceptance(repo)
    bad_binding = binding.model_copy(update={"frontier_digest": "sha256:not-the-base"})

    with pytest.raises(RuntimeContractError, match="exact base snapshot frontier"):
        repo.commit_pnca_acceptance(
            slug="series",
            acceptance=acceptance,
            frontier_binding=bad_binding,
        )


def test_committed_operation_is_idempotent_on_resume(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    acceptance, binding, _base, _output = _prepared_scene_acceptance(repo)

    first = repo.commit_pnca_acceptance(
        slug="series",
        acceptance=acceptance,
        frontier_binding=binding,
    )
    second = repo.commit_pnca_acceptance(
        slug="series",
        acceptance=acceptance,
        frontier_binding=binding,
    )

    assert second.selection_snapshot_id == first.selection_snapshot_id


def test_operation_key_reuse_with_different_base_snapshot_is_superseded(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    acceptance, binding, base, _output = _prepared_scene_acceptance(repo)
    repo.commit_pnca_acceptance(slug="series", acceptance=acceptance, frontier_binding=binding)
    conflicting = acceptance.model_copy(update={"base_snapshot_id": f"{base.selection_snapshot_id}-other"})

    with pytest.raises(RuntimeContractError, match="superseded"):
        repo.commit_pnca_acceptance(slug="series", acceptance=conflicting, frontier_binding=binding)
