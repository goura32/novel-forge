"""PNCA progressive contract authoring tests."""

from __future__ import annotations

from novel_forge.pnca.contracts import (
    AdmissionAllowance,
    ChapterContract,
    FrontierBinding,
    SeriesContract,
    SeriesContractProposal,
    VolumeContract,
    VolumePurpose,
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


def _executor(outputs, projections: list[dict] | None = None):
    def provider(task_id, projection, operation_key):
        if projections is not None:
            projections.append(projection)
        return outputs[task_id]

    specs = tuple(
        TaskSpec(
            task_id=task_id,
            task_kind="authoring",
            input_bindings=(
                (
                    InputBinding(role="parent.contract", variable="parent"),
                    InputBinding(role="canon.frontier", variable="frontier"),
                    InputBinding(role="canon.projection", variable="canon_projection"),
                    InputBinding(role="admission.allowances", variable="admission_allowances"),
                    InputBinding(role="scene.request", variable="request"),
                )
                if task_id == "pnca.scene.contract"
                else (InputBinding(role="series.request", variable="request"),)
                if task_id == "pnca.series.contract"
                else (InputBinding(role="parent.contract", variable="parent"), InputBinding(role="volume.request", variable="request"))
                if task_id == "pnca.volume.contract"
                else (InputBinding(role="parent.contract", variable="parent"), InputBinding(role="chapter.request", variable="request"))
                if task_id == "pnca.chapter.contract"
                else (InputBinding(role="parent.contract", variable="parent"),)
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
            "volume_purposes": [{"ordinal": 1, "purpose": "呪いの受諾"}],
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
            "scene_slots": [
                {"slot_id": "scene_001", "ordinal": 1, "allowed_admission_allowance_ids": ["allow_artifact"]}
            ],
        },
    }
    author = PNCAContractAuthor(repository=repo, executor=_executor(outputs))

    request = repo.commit_artifact(
        repo.start_attempt(run, task_id="request", phase="plan", reason="test"),
        artifact_type="pnca.series.request",
        logical_key="pnca.series.request.series_001",
        payload={"slug": "series_001"},
        payload_name="request.json",
    )
    series = author.author_series(run=run, scope_id="series_001", request=request)
    volume_request = repo.commit_artifact(
        repo.start_attempt(run, task_id="volume-request", phase="design", reason="test"),
        artifact_type="pnca.volume.request",
        logical_key="pnca.volume.request.001",
        payload={"volume_ordinal": 1},
        payload_name="request.json",
    )
    volume = author.author_volume(run=run, parent=series, request=volume_request, scope_id="volume_001")
    chapter_request = repo.commit_artifact(
        repo.start_attempt(run, task_id="chapter-request", phase="design", reason="test"),
        artifact_type="pnca.chapter.request",
        logical_key="pnca.chapter.request.volume_001.001",
        payload={"chapter_ordinal": 1},
        payload_name="request.json",
    )
    chapter = author.author_chapter(run=run, parent=volume, request=chapter_request, scope_id="chapter_001")

    assert isinstance(repo.read_payload(series.artifact), dict)
    assert isinstance(series.contract, SeriesContract)
    assert volume.artifact.manifest.input_artifact_ids == (series.artifact.artifact_id, volume_request.artifact_id)
    assert isinstance(volume.contract, VolumeContract)
    assert volume.contract.purpose == "呪いの受諾"
    assert chapter.artifact.manifest.input_artifact_ids == (volume.artifact.artifact_id, chapter_request.artifact_id)
    assert isinstance(chapter.contract, ChapterContract)
    assert chapter.contract.volume_purpose == "呪いの受諾"



def test_volume_authoring_requires_a_pinned_volume_request(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="design", model="fake", verbose=False, input_snapshot_id="snap_001")
    series = SeriesContract(
        contract_id="series_001",
        canon_seed_artifact_id="art_seed",
        root_frontier_artifact_id="art_frontier",
        root_frontier_digest="sha256:root",
        volume_purposes=(VolumePurpose(ordinal=1, purpose="呪いの受諾"),),
    )
    series_artifact = repo.commit_artifact(
        repo.start_attempt(run, task_id="series", phase="plan", reason="test"),
        artifact_type="pnca.series.contract",
        logical_key="pnca.series.contract.series_001",
        payload=series.model_dump(mode="json"),
        payload_name="contract.json",
    )
    request = repo.commit_artifact(
        repo.start_attempt(run, task_id="request", phase="design", reason="test"),
        artifact_type="pnca.volume.request",
        logical_key="pnca.volume.request.001",
        payload={"volume_ordinal": 1},
        payload_name="request.json",
    )
    author = PNCAContractAuthor(
        repository=repo,
        executor=_executor(
            {
                "pnca.volume.contract": {
                    "contract_id": "volume_001",
                    "parent_series_contract_id": "series_001",
                    "volume_ordinal": 1,
                }
            }
        ),
    )

    volume = author.author_volume(
        run=run,
        parent=AuthoredContract(artifact=series_artifact, contract=series),
        request=request,
        scope_id="volume_001",
    )

    assert volume.artifact.manifest.input_artifact_ids == (series_artifact.artifact_id, request.artifact_id)
    assert volume.contract.volume_ordinal == 1

    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)
    author = PNCAContractAuthor(
        repository=repo,
        executor=_executor(
            {
                "pnca.series.contract": {
                    "contract_id": "series_001",
                    "canon_seed": {"schema_version": 2, "series": {"id": "series_001"}},
                    "volume_purposes": [{"ordinal": 1, "purpose": "魔女が月灯りの呪いを引き受ける"}],
                }
            }
        ),
    )

    request = repo.commit_artifact(
        repo.start_attempt(run, task_id="request", phase="plan", reason="test"),
        artifact_type="pnca.series.request",
        logical_key="pnca.series.request.series_001",
        payload={"slug": "series_001"},
        payload_name="request.json",
    )
    series = author.author_series(run=run, scope_id="series_001", request=request)

    assert isinstance(
        SeriesContractProposal(
            contract_id="series_001",
            canon_seed={"seed": True},
            volume_purposes=(VolumePurpose(ordinal=1, purpose="呪いの受諾"),),
        ),
        SeriesContractProposal,
    )
    seed = repo.verify_artifact(series.contract.canon_seed_artifact_id)
    frontier = repo.verify_artifact(series.contract.root_frontier_artifact_id)
    assert seed.manifest.artifact_type == "canon.seed"
    assert frontier.manifest.logical_key == "canon.frontier.root"
    assert frontier.manifest.canon_lineage_root_digest == seed.manifest.content_digest
    assert series.contract.root_frontier_digest == frontier.manifest.content_digest
    assert series.contract.volume_purposes[0].purpose == "魔女が月灯りの呪いを引き受ける"
    assert repo.read_payload(series.artifact)["volume_purposes"] == [{"ordinal": 1, "purpose": "魔女が月灯りの呪いを引き受ける"}]
    assert series.artifact.manifest.input_artifact_ids == (request.artifact_id, seed.artifact_id, frontier.artifact_id)


def test_scene_authoring_requires_parent_slot_and_exact_frontier(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)
    seed = repo.commit_artifact(
        repo.start_attempt(run, task_id="seed-root", phase="plan", reason="test"),
        artifact_type="canon.seed",
        logical_key="canon.seed",
        payload={"title": "test seed"},
        payload_name="seed.json",
    )
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
            "scene_slots": [
                {"slot_id": "scene_001", "ordinal": 1, "allowed_admission_allowance_ids": ["allow_artifact"]}
            ],
        },
        "pnca.scene.contract": {
            "contract_id": "scene_contract_001",
            "slot_id": "scene_001",
            "canon_effect": "mutates",
            "canon_patch": {"scene_progress": "契約を受け入れた"},
        },
    }
    volume = VolumeContract(
        contract_id="volume_001",
        parent_series_contract_id="series_001",
        volume_ordinal=1,
        purpose="呪いを解き幸福へ至る",
        admission_allowances=(
            AdmissionAllowance(allowance_id="allow_character", kind="character", max_count=1),
            AdmissionAllowance(allowance_id="allow_artifact", kind="artifact", max_count=1),
        ),
    )
    volume_artifact = repo.commit_artifact(
        repo.start_attempt(run, task_id="volume", phase="design", reason="test"),
        artifact_type="pnca.volume.contract",
        logical_key="pnca.volume.contract.volume_001",
        payload=volume.model_dump(mode="json"),
        payload_name="volume.json",
    )
    chapter_request = repo.commit_artifact(
        repo.start_attempt(run, task_id="chapter-request", phase="design", reason="test"),
        artifact_type="pnca.chapter.request",
        logical_key="pnca.chapter.request.volume_001.001",
        payload={"chapter_ordinal": 1},
        payload_name="request.json",
    )
    projections: list[dict] = []
    author = PNCAContractAuthor(repository=repo, executor=_executor(outputs, projections))
    chapter = author.author_chapter(
        run=run,
        parent=AuthoredContract(artifact=volume_artifact, contract=volume),
        request=chapter_request,
        scope_id="chapter_001",
    )
    binding = FrontierBinding(
        input_snapshot_id="snap_001",
        frontier_artifact_id=frontier.artifact_id,
        frontier_digest=frontier.manifest.content_digest,
        lineage_root_digest=seed.manifest.content_digest,
    )

    scene_request = repo.commit_artifact(
        repo.start_attempt(run, task_id="scene-request", phase="design", reason="test"),
        artifact_type="pnca.scene.request",
        logical_key="pnca.scene.request.chapter_001.scene_001",
        payload={"slot_id": "scene_001"},
        payload_name="request.json",
    )

    scene, _consumed = author.author_scene(
        run=run,
        parent=chapter,
        request=scene_request,
        frontier=frontier,
        frontier_binding=binding,
        scope_id="scene_001",
        admission_allowances=volume.admission_allowances,
        scene_slot=chapter.contract.scene_slots[0],
    )

    assert scene.artifact.manifest.input_artifact_ids == (
        chapter.artifact.artifact_id,
        frontier.artifact_id,
        scene_request.artifact_id,
    )
    assert scene.contract.slot_id == "scene_001"
    assert scene.contract.writer_view.narrative_contract["parent_volume_purpose"] == "呪いを解き幸福へ至る"
    assert projections[-1]["admission_allowances"] == [
        {"allowance_id": "allow_artifact", "kind": "artifact", "max_count": 1}
    ]
