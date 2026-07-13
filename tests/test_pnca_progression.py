"""PNCA progressive contract authoring tests."""

from __future__ import annotations

from novel_forge.pnca.contracts import ChapterContract, SeriesContract, VolumeContract
from novel_forge.pnca.progression import PNCAContractAuthor
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
            input_bindings=(InputBinding(role="parent.contract", variable="parent"),) if task_id != "pnca.series.contract" else (),
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
            "canon_seed_artifact_id": "seed_001",
            "root_frontier_artifact_id": "frontier_001",
            "root_frontier_digest": "sha256:root",
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
