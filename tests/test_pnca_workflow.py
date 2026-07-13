"""Public PNCA workflow boundaries."""

from __future__ import annotations

from novel_forge.pnca.contracts import SeriesContract
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
    )
    contract_artifact = repo.commit_artifact(
        repo.start_attempt(run, task_id="series", phase="plan", reason="test"),
        artifact_type="pnca.series.contract",
        logical_key="pnca.series.contract.series_001",
        payload=contract.model_dump(mode="json"),
        payload_name="contract.json",
        input_artifact_ids=(seed.artifact_id, frontier.artifact_id),
    )

    class FakeAuthor:
        def author_series(self, *, run, scope_id):
            assert run is not None
            assert scope_id == "series_001"
            return AuthoredContract(artifact=contract_artifact, contract=contract)

    result = PNCAWorkflow(repository=repo, contract_author=FakeAuthor()).bootstrap_series(
        run=run,
        slug="series_001",
        scope_id="series_001",
    )

    assert result.selection_snapshot_id == repo.current_snapshot_id("series_001")
    assert result.slots["pnca.series.contract.series_001"] == contract_artifact.artifact_id
