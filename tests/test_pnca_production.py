from __future__ import annotations

from novel_forge.pnca.production import make_pnca_task_executor, stage_series_request
from novel_forge.runtime import RunRepository


def test_stage_series_request_persists_only_cli_intent_as_an_artifact(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)

    request = stage_series_request(
        repository=repo,
        run=run,
        slug="moon_lantern",
        keywords="月灯りの魔女",
        existing_slugs=("old_series",),
    )

    assert request.manifest.artifact_type == "pnca.series.request"
    assert request.manifest.logical_key == "pnca.series.request.moon_lantern"
    assert repo.read_payload(request) == {
        "slug": "moon_lantern",
        "keywords": "月灯りの魔女",
        "existing_slugs": ["old_series"],
    }


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
    assert "pnca.series.contract" not in calls[0]["user_prompt"]
