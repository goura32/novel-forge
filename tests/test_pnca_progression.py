"""PNCA progressive contract authoring tests."""

from __future__ import annotations

from novel_forge.pnca.contracts import (
    ChapterContract,
    FrontierBinding,
    SeriesContract,
    SeriesContractProposal,
    VolumeContract,
)
from novel_forge.pnca.progression import AuthoredContract, PNCAContractAuthor
from novel_forge.pnca.registry import (
    ArtifactSpec,
    InputBinding,
    PNCATaskExecutor,
    PNCATaskRegistry,
    TaskSpec,
)
from novel_forge.runtime import RunRepository


def _executor(outputs):
    def provider(task_id, projection, operation_key):
        return outputs[task_id]

    specs = tuple(
        TaskSpec(
            task_id=task_id,
            task_kind="authoring",
            input_bindings=(
                (InputBinding(role="parent.contract", variable="parent"), InputBinding(role="canon.frontier", variable="frontier"))
                if task_id == "pnca.scene.contract"
                else (InputBinding(role="parent.contract", variable="parent"),)
                if task_id != "pnca.series.contract"
                else ()
            ),
            output=ArtifactSpec(role=task_id, artifact_type="pnca.contract", logical_key_template=f"{task_id}.{{scope_id}}"),
            prompt_digest="sha256:prompt",
            schema_digest="sha256:schema",
            model_profile="fake",
            max_input_bytes=4096,
            max_output_bytes=4096,
            idempotency_scope="contract",
        )
        for task_id in outputs
    )
    return PNCATaskExecutor(registry=PNCATaskRegistry(specs=specs), provider=provider)


def test_progression_persists_parent_pinned_contract_artifacts(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)
    outputs = {
        "pnca.series.contract": {
            "contract_id": "series_001",
            "canon_seed": {"schema_version": 2, "series": {"id": "series_001"}},
        },
        "pnca.volume.contract": {
            "contract_id": "volume_001",
            "parent_series_contract_id": "series_001",
            "volume_ordinal": 1,
        },
        "pnca.chapter.contract": {
            "contract_id": "chapter_001",
            "parent_volume_contract_id": "volume_001",
            "chapter_ordinal": 1,
            "scene_slots": [{"slot_id": "scene_001", "ordinal": 1}],
        },
    }
    author = PNCAContractAuthor(repository=repo, executor=_executor(outputs))

    series = author.author_series(run=run, scope_id="series_001")
    volume = author.author_volume(run=run, parent=series, scope_id="volume_001")
    chapter = author.author_chapter(run=run, parent=volume, scope_id="chapter_001")

    assert isinstance(repo.read_payload(series.artifact), dict)
    assert isinstance(series.contract, SeriesContract)
    assert volume.artifact.manifest.input_artifact_ids == (series.artifact.artifact_id,)
    assert isinstance(volume.contract, VolumeContract)
    assert chapter.artifact.manifest.input_artifact_ids == (volume.artifact.artifact_id,)
    assert isinstance(chapter.contract, ChapterContract)


def test_series_authoring_materializes_seed_and_root_frontier_before_contract(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)
    author = PNCAContractAuthor(
        repository=repo,
        executor=_executor(
            {
                "pnca.series.contract": {
                    "contract_id": "series_001",
                    "canon_seed": {"schema_version": 2, "series": {"id": "series_001"}},
                }
            }
        ),
    )

    series = author.author_series(run=run, scope_id="series_001")

    assert isinstance(SeriesContractProposal(contract_id="series_001", canon_seed={"seed": True}), SeriesContractProposal)
    seed = repo.verify_artifact(series.contract.canon_seed_artifact_id)
    frontier = repo.verify_artifact(series.contract.root_frontier_artifact_id)
    assert seed.manifest.artifact_type == "canon.seed"
    assert frontier.manifest.logical_key == "canon.frontier.root"
    assert frontier.manifest.canon_lineage_root_digest == seed.manifest.content_digest
    assert series.contract.root_frontier_digest == frontier.manifest.content_digest
    assert series.artifact.manifest.input_artifact_ids == (seed.artifact_id, frontier.artifact_id)


def test_scene_authoring_requires_parent_slot_and_exact_frontier(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)
    frontier_attempt = repo.start_attempt(run, task_id="seed", phase="plan", reason="test")
    frontier = repo.commit_artifact(
        frontier_attempt,
        artifact_type="canon.event_set",
        logical_key="canon.frontier.root",
        payload={"events": []},
        payload_name="frontier.json",
    )
    outputs = {
        "pnca.chapter.contract": {
            "contract_id": "chapter_001",
            "parent_volume_contract_id": "volume_001",
            "chapter_ordinal": 1,
            "scene_slots": [{"slot_id": "scene_001", "ordinal": 1}],
        },
        "pnca.scene.contract": {
            "contract_id": "scene_contract_001",
            "slot_id": "scene_001",
            "frontier_binding": {
                "input_snapshot_id": "snap_001",
                "frontier_artifact_id": frontier.artifact_id,
                "frontier_digest": frontier.manifest.content_digest,
                "lineage_root_digest": "sha256:root",
            },
            "canon_effect": "none",
        },
    }
    volume = VolumeContract(contract_id="volume_001", parent_series_contract_id="series_001", volume_ordinal=1)
    volume_artifact = repo.commit_artifact(
        repo.start_attempt(run, task_id="volume", phase="design", reason="test"),
        artifact_type="pnca.volume.contract",
        logical_key="pnca.volume.contract.volume_001",
        payload=volume.model_dump(mode="json"),
        payload_name="volume.json",
    )
    author = PNCAContractAuthor(repository=repo, executor=_executor(outputs))
    chapter = author.author_chapter(
        run=run,
        parent=AuthoredContract(artifact=volume_artifact, contract=volume),
        scope_id="chapter_001",
    )
    binding = FrontierBinding(
        input_snapshot_id="snap_001",
        frontier_artifact_id=frontier.artifact_id,
        frontier_digest=frontier.manifest.content_digest,
        lineage_root_digest="sha256:root",
    )

    scene = author.author_scene(
        run=run,
        parent=chapter,
        slot_id="scene_001",
        frontier=frontier,
        frontier_binding=binding,
        scope_id="scene_001",
    )

    assert scene.artifact.manifest.input_artifact_ids == (chapter.artifact.artifact_id, frontier.artifact_id)
    assert scene.contract.slot_id == "scene_001"
