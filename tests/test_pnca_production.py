from __future__ import annotations

import pytest

from novel_forge.pnca.contracts import SeriesContractProposal
from novel_forge.pnca.production import (
    make_pnca_task_executor,
    stage_chapter_request,
    stage_scene_request,
    stage_series_request,
)
from novel_forge.runtime import RunRepository


def test_stage_series_request_persists_only_cli_intent_as_an_artifact(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)

    request = stage_series_request(
        repository=repo,
        run=run,
        request_id=run.manifest.run_id,
        keywords="月灯りの魔女",
        existing_slugs=("old_series",),
        volume_count=3,
    )

    assert request.manifest.artifact_type == "pnca.series.request"
    assert request.manifest.logical_key == f"pnca.series.request.{run.manifest.run_id}"
    assert repo.read_payload(request) == {
        "keywords": "月灯りの魔女",
        "existing_slugs": ["old_series"],
        "volume_count": 3,
    }


def test_stage_chapter_request_persists_only_chapter_target_as_an_artifact(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="design", model="fake", verbose=False, input_snapshot_id="snap_001")

    request = stage_chapter_request(
        repository=repo,
        run=run,
        volume_id="volume_001",
        chapter_ordinal=2,
    )

    assert request.manifest.artifact_type == "pnca.chapter.request"
    assert request.manifest.logical_key == "pnca.chapter.request.volume_001.002"
    assert repo.read_payload(request) == {"chapter_ordinal": 2}


def test_stage_scene_request_persists_terminal_role_with_chapter_slot_as_an_artifact(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="design", model="fake", verbose=False, input_snapshot_id="snap_001")

    request = stage_scene_request(
        repository=repo,
        run=run,
        chapter_id="chapter_001",
        slot_id="scene_002",
        is_terminal_scene=True,
    )

    assert request.manifest.artifact_type == "pnca.scene.request"
    assert request.manifest.logical_key == "pnca.scene.request.chapter_001.scene_002"
    assert repo.read_payload(request) == {"slot_id": "scene_002", "is_terminal_scene": True}


def test_series_proposal_rejects_an_unsafe_final_slug() -> None:
    with pytest.raises(ValueError, match="string_pattern_mismatch"):
        SeriesContractProposal(contract_id="../escape", canon_seed={"series": {"id": "escape"}})


def test_production_executor_renders_only_registered_request_projection() -> None:
    calls: list[dict] = []

    class FakeClient:
        def complete_json(self, **kwargs):
            calls.append(kwargs)
            return {"contract_id": "moon_lantern", "canon_seed": {"series": {"id": "moon_lantern"}}}

    executor = make_pnca_task_executor(client=FakeClient())
    result = executor.execute(
        task_id="pnca.series.contract",
        scope_id="moon_lantern",
        artifacts={
            "series.request": {
                "slug": "moon_lantern",
                "keywords": "月灯りの魔女",
                "existing_slugs": [],
            }
        },
        input_artifact_ids=("art_request",),
    )

    assert result["contract_id"] == "moon_lantern"
    assert calls[0]["kind"] == "pnca.series.contract"
    assert "月灯りの魔女" in calls[0]["user_prompt"]


def test_production_executor_captures_one_terminal_llm_attempt(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)

    class CapturingFakeClient:
        def __init__(self) -> None:
            self.capture = None

        def with_capture(self, capture):
            self.capture = capture
            return self

        def complete_json(self, **kwargs):
            assert self.capture is not None
            payload = {"model": "fake", "messages": [{"role": "user", "content": kwargs["user_prompt"]}]}
            value = {"contract_id": "moon_lantern", "canon_seed": {"series": {"id": "moon_lantern"}}}
            self.capture.request(payload)
            self.capture.response_ndjson([{"message": {"content": "{}"}}])
            self.capture.response_content("{}")
            self.capture.parsed(value)
            self.capture.validation({"outcome": "passed"})
            return value

    executor = make_pnca_task_executor(client=CapturingFakeClient(), repository=repo, run=run)
    executor.execute(
        task_id="pnca.series.contract",
        scope_id="moon_lantern",
        artifacts={"series.request": {"slug": "moon_lantern", "keywords": "月灯りの魔女", "existing_slugs": []}},
        input_artifact_ids=("art_request",),
    )
    llm_attempts = list((run.path / "attempts").glob("*/llm/request.json"))
    assert len(llm_attempts) == 1
    attempt_path = llm_attempts[0].parent.parent
    assert (attempt_path / "llm/response.ndjson").is_file()
    assert (attempt_path / "llm/parsed.json").is_file()
    assert (attempt_path / "llm/validation.json").is_file()
    assert (attempt_path / "completion.json").is_file()


def test_production_executor_renders_only_registered_volume_projection() -> None:
    calls: list[dict] = []

    class FakeClient:
        def complete_json(self, **kwargs):
            calls.append(kwargs)
            return {"contract_id": "volume_001", "parent_series_contract_id": "series_001", "volume_ordinal": 1}

    executor = make_pnca_task_executor(client=FakeClient())
    result = executor.execute(
        task_id="pnca.volume.contract",
        scope_id="volume_001",
        artifacts={
            "parent.contract": {"contract_id": "series_001", "volume_purposes": [{"ordinal": 1, "purpose": "受諾"}]},
            "volume.request": {"volume_ordinal": 1},
        },
        input_artifact_ids=("art_series", "art_request"),
    )

    assert result["parent_series_contract_id"] == "series_001"
    assert calls[0]["kind"] == "pnca.volume.contract"
    assert "series_001" in calls[0]["user_prompt"]
    assert "volume_001" not in calls[0]["user_prompt"]


def test_production_executor_renders_only_registered_scene_projection() -> None:
    calls: list[dict] = []

    class FakeClient:
        def complete_json(self, **kwargs):
            calls.append(kwargs)
            return {
                "contract_id": "scene_contract_001",
                "slot_id": "scene_001",
                "canon_effect": "none",
                "writer_view": {
                    "start_context": {},
                    "narrative_contract": {},
                    "end_constraints": {},
                    "presentation_constraints": {},
                },
            }

    executor = make_pnca_task_executor(client=FakeClient())
    result = executor.execute(
        task_id="pnca.scene.contract",
        scope_id="scene_001",
        artifacts={
            "parent.contract": {"contract_id": "chapter_001", "scene_slots": [{"slot_id": "scene_001", "ordinal": 1}]},
            "canon.frontier": {"events": [{"event": "known"}]},
            "canon.projection": {"seed": {"title": "seed"}, "events": [{"event": "known"}]},
            "admission.allowances": [{"allowance_id": "allow_relic", "kind": "artifact", "max_count": 1}],
            "scene.request": {"slot_id": "scene_001"},
        },
        input_artifact_ids=("art_chapter", "art_frontier", "art_request"),
    )

    assert result["slot_id"] == "scene_001"
    assert calls[0]["kind"] == "pnca.scene.contract"
    assert "chapter_001" in calls[0]["user_prompt"]
    assert '"event": "known"' in calls[0]["user_prompt"]


def test_production_executor_passes_required_scene_beats_to_renderer() -> None:
    calls: list[dict] = []

    class FakeClient:
        def complete_json(self, **kwargs):
            calls.append(kwargs)
            return {"content": "本文"}

    executor = make_pnca_task_executor(client=FakeClient())
    executor.execute(
        task_id="pnca.scene.render",
        scope_id="scene_001",
        artifacts={
            "writer.view": {
                "start_context": {},
                "narrative_contract": {},
                "end_constraints": {},
                "presentation_constraints": {},
                "required_beats": ["エリナが契約を提案する", "公爵が条件付きで受諾する"],
            }
        },
        input_artifact_ids=("art_view",),
    )

    assert '"エリナが契約を提案する"' in calls[0]["user_prompt"]
    assert '"公爵が条件付きで受諾する"' in calls[0]["user_prompt"]
