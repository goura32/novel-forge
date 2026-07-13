"""Public PNCA workflow boundaries."""

from __future__ import annotations

from types import SimpleNamespace

import novel_forge.pnca.workflow as workflow_module
from novel_forge.pnca.contracts import (
    AcceptanceCommit,
    ChapterContract,
    FrontierBinding,
    SeriesContract,
    VolumePurpose,
)
from novel_forge.pnca.progression import AuthoredContract
from novel_forge.pnca.workflow import PNCAWorkflow
from novel_forge.runtime import RunRepository


def test_bootstrap_series_authors_then_selects_pnca_root(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)
    seed = repo.commit_artifact(
        repo.start_attempt(run, task_id="seed", phase="plan", reason="test"),
        artifact_type="canon.seed",
        logical_key="canon.seed",
        payload={"seed": True},
        payload_name="seed.json",
    )
    frontier = repo.commit_artifact(
        repo.start_attempt(run, task_id="frontier", phase="plan", reason="test"),
        artifact_type="canon.event_set",
        logical_key="canon.frontier.root",
        payload={"events": []},
        payload_name="frontier.json",
        canon_lineage_root_digest=seed.manifest.content_digest,
    )
    contract = SeriesContract(
        contract_id="series_001",
        canon_seed_artifact_id=seed.artifact_id,
        root_frontier_artifact_id=frontier.artifact_id,
        root_frontier_digest=frontier.manifest.content_digest,
        volume_purposes=(VolumePurpose(ordinal=1, purpose="呪いの受諾"),),
    )
    contract_artifact = repo.commit_artifact(
        repo.start_attempt(run, task_id="series", phase="plan", reason="test"),
        artifact_type="pnca.series.contract",
        logical_key="pnca.series.contract.series_001",
        payload=contract.model_dump(mode="json"),
        payload_name="contract.json",
        input_artifact_ids=(seed.artifact_id, frontier.artifact_id),
    )

    request = repo.commit_artifact(
        repo.start_attempt(run, task_id="request", phase="plan", reason="test"),
        artifact_type="pnca.series.request",
        logical_key="pnca.series.request.series_001",
        payload={"slug": "series_001"},
        payload_name="request.json",
    )

    class FakeAuthor:
        def author_series(self, *, run, scope_id, request):
            assert run is not None
            assert scope_id == "series_001"
            assert request.artifact_id == request_artifact.artifact_id
            return AuthoredContract(artifact=contract_artifact, contract=contract)

    request_artifact = request
    workflow = PNCAWorkflow(repository=repo, contract_author=FakeAuthor())
    authored = workflow.author_series(run=run, scope_id="series_001", request=request_artifact)
    result = workflow.accept_series(authored=authored)

    assert result.selection_snapshot_id == repo.current_snapshot_id("series_001")
    assert result.slots["pnca.series.contract.series_001"] == contract_artifact.artifact_id


def test_accept_chapter_delegates_to_parent_pinned_repository_transaction() -> None:
    captured: dict[str, object] = {}

    class FakeRepository:
        @staticmethod
        def commit_pnca_chapter_acceptance(*, slug, acceptance):
            captured.update({"slug": slug, "acceptance": acceptance})
            return SimpleNamespace(selection_snapshot_id="sel_chapter")

    chapter = ChapterContract(
        contract_id="chapter_001",
        parent_volume_contract_id="volume_002",
        chapter_ordinal=1,
        scene_slots=(),
    )
    authored = AuthoredContract(
        artifact=SimpleNamespace(artifact_id="art_chapter"),
        contract=chapter,
    )

    result = PNCAWorkflow(repository=FakeRepository(), contract_author=object()).accept_chapter(
        slug="series_001",
        authored=authored,
        base_snapshot_id="sel_volume",
        volume_ordinal=2,
    )

    assert result.selection_snapshot_id == "sel_chapter"
    assert captured["slug"] == "series_001"
    acceptance = captured["acceptance"]
    assert acceptance.base_snapshot_id == "sel_volume"
    assert acceptance.role_artifact_ids == {"chapter.contract": "art_chapter"}
    assert acceptance.operation_key == "series_001:volume:002:chapter:001:accept"


def test_author_scene_delegates_only_pinned_request_and_frontier_inputs() -> None:
    captured: dict[str, object] = {}

    class FakeAuthor:
        @staticmethod
        def author_scene(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(contract=SimpleNamespace(contract_id="scene_001")), ()

    parent = AuthoredContract(
        artifact=SimpleNamespace(artifact_id="art_chapter"),
        contract=ChapterContract(
            contract_id="chapter_001",
            parent_volume_contract_id="volume_001",
            chapter_ordinal=1,
            scene_slots=(),
        ),
    )
    request = SimpleNamespace(artifact_id="art_request")
    frontier = SimpleNamespace(artifact_id="art_frontier")
    binding = FrontierBinding(
        input_snapshot_id="sel_chapter",
        frontier_artifact_id="art_frontier",
        frontier_digest="sha256:frontier",
        lineage_root_digest="sha256:seed",
    )

    result, consumed = PNCAWorkflow(repository=object(), contract_author=FakeAuthor()).author_scene(
        run=SimpleNamespace(run_id="run_001"),
        parent=parent,
        request=request,
        frontier=frontier,
        frontier_binding=binding,
        scope_id="scene_001",
    )

    assert result.contract.contract_id == "scene_001"
    assert consumed == ()
    assert captured == {
        "run": SimpleNamespace(run_id="run_001"),
        "parent": parent,
        "request": request,
        "frontier": frontier,
        "frontier_binding": binding,
        "scope_id": "scene_001",
        "admission_allowances": (),
        "scene_slot": None,
        "previously_consumed": (),
    }


def test_accept_scene_delegates_complete_commit_and_exact_frontier_binding() -> None:
    captured: dict[str, object] = {}

    class FakeRepository:
        @staticmethod
        def commit_pnca_acceptance(*, slug, acceptance, frontier_binding):
            captured.update(
                {
                    "slug": slug,
                    "acceptance": acceptance,
                    "frontier_binding": frontier_binding,
                }
            )
            return SimpleNamespace(selection_snapshot_id="sel_scene")

    acceptance = AcceptanceCommit(
        acceptance_id="accept_scene_001",
        base_snapshot_id="sel_chapter",
        operation_key="series_001:scene:scene_001:accept",
        canon_effect="none",
        role_artifact_ids={
            "scene.contract": "art_scene",
            "parent.requirement_ledger": "art_parent_ledger",
            "accepted.requirement_ledger": "art_accepted_ledger",
            "audit.batch": "art_audits",
            "review.synthesis": "art_review",
            "scene.slot_binding": "art_slot",
            "canon.frontier.output": "art_frontier",
        },
    )
    binding = FrontierBinding(
        input_snapshot_id="sel_chapter",
        frontier_artifact_id="art_frontier",
        frontier_digest="sha256:frontier",
        lineage_root_digest="sha256:seed",
    )

    result = PNCAWorkflow(repository=FakeRepository(), contract_author=object()).accept_scene(
        slug="series_001",
        acceptance=acceptance,
        frontier_binding=binding,
    )

    assert result.selection_snapshot_id == "sel_scene"
    assert captured == {
        "slug": "series_001",
        "acceptance": acceptance,
        "frontier_binding": binding,
    }


def test_build_scene_acceptance_assembles_complete_role_group(monkeypatch) -> None:
    prepared_structure = SimpleNamespace(
        role_artifact_ids={
            "scene.contract": "art_scene",
            "parent.requirement_ledger": "art_parent_ledger",
            "accepted.requirement_ledger": "art_accepted_ledger",
            "scene.slot_binding": "art_slot",
            "canon.frontier.output": "art_frontier",
        }
    )
    prepared_audit = SimpleNamespace(
        batch=SimpleNamespace(artifact_id="art_audit"),
        synthesis=SimpleNamespace(artifact_id="art_review"),
    )

    class FakeStructure:
        def __init__(self, *, repository):
            self.repository = repository

        def prepare(self, **kwargs):
            return prepared_structure

    class FakeAudit:
        def __init__(self, *, repository):
            self.repository = repository

        def run_structural_audit(self, **kwargs):
            return prepared_audit

    monkeypatch.setattr(workflow_module, "PNCASceneStructurePreparer", FakeStructure)
    monkeypatch.setattr(workflow_module, "PNCASceneAuditSynthesizer", FakeAudit)

    workflow = PNCAWorkflow(repository=object(), contract_author=object())
    acceptance = workflow.build_scene_acceptance(
        slug="series_001",
        run=SimpleNamespace(run_id="run_001"),
        scene=SimpleNamespace(contract=SimpleNamespace(contract_id="scene_contract_001", canon_effect="none")),
        parent_chapter=SimpleNamespace(artifact=SimpleNamespace(artifact_id="art_chapter")),
        parent_volume=SimpleNamespace(artifact=SimpleNamespace(artifact_id="art_volume")),
        frontier_binding=FrontierBinding(
            input_snapshot_id="sel_chapter",
            frontier_artifact_id="art_frontier",
            frontier_digest="sha256:frontier",
            lineage_root_digest="sha256:seed",
        ),
        base_snapshot_id="sel_chapter",
    )

    assert acceptance.canon_effect == "none"
    assert acceptance.base_snapshot_id == "sel_chapter"
    assert acceptance.operation_key == "series_001:scene:scene_contract_001:accept"
    assert acceptance.role_artifact_ids == {
        "scene.contract": "art_scene",
        "parent.requirement_ledger": "art_parent_ledger",
        "accepted.requirement_ledger": "art_accepted_ledger",
        "audit.batch": "art_audit",
        "review.synthesis": "art_review",
        "scene.slot_binding": "art_slot",
        "canon.frontier.output": "art_frontier",
    }


def test_prepare_scene_structure_delegates_only_pinned_contracts(monkeypatch) -> None:
    captured: dict[str, object] = {}
    prepared = SimpleNamespace(role_artifact_ids={"scene.contract": "art_scene"})

    class FakePreparer:
        def __init__(self, *, repository) -> None:
            captured["repository"] = repository

        def prepare(self, **kwargs):
            captured.update(kwargs)
            return prepared

    monkeypatch.setattr(workflow_module, "PNCASceneStructurePreparer", FakePreparer)
    repository = object()
    run = SimpleNamespace(run_id="run_001")
    scene = SimpleNamespace(artifact=SimpleNamespace(artifact_id="art_scene"))
    chapter = SimpleNamespace(artifact=SimpleNamespace(artifact_id="art_chapter"))
    volume = SimpleNamespace(artifact=SimpleNamespace(artifact_id="art_volume"))

    result = PNCAWorkflow(repository=repository, contract_author=object()).prepare_scene_structure(
        slug="series_001",
        run=run,
        scene=scene,
        parent_chapter=chapter,
        parent_volume=volume,
    )

    assert result is prepared
    assert captured == {
        "repository": repository,
        "slug": "series_001",
        "run": run,
        "scene": scene,
        "parent_chapter": chapter,
        "parent_volume": volume,
    }
