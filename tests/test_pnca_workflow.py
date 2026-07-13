"""Public PNCA workflow boundaries."""

from __future__ import annotations

from types import SimpleNamespace

from novel_forge.pnca.contracts import ChapterContract, SeriesContract, VolumePurpose
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
