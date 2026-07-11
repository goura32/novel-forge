"""Plan generation must retain its real LLM attempt as the selected plan artifact."""

from __future__ import annotations

from novel_forge.canon.store import BibleFactory
from novel_forge.runtime import RunRepository
from novel_forge.workflow_runtime import RuntimeWorkflow


def test_bootstrap_commits_selected_plan_from_generation_attempt(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)
    plan = {"title": "Series", "slug": "series", "planned_volumes": [{"number": 1, "title": "Vol"}]}
    workflow = RuntimeWorkflow(repo, run, task_runner=lambda _task, _values: plan)

    attempt, generated = workflow._run_task("plan.series.generate", {}, reason="generate series plan")
    snapshot = workflow.bootstrap_plan(
        slug="series",
        plan=generated,
        canon_seed=BibleFactory.create_seed(plan).model_dump(mode="json"),
        plan_attempt=attempt,
    )

    plan_ref = repo.verify_artifact(snapshot.slots["plan.series"])
    attempts = list((run.path / "attempts").iterdir())
    assert plan_ref.attempt_id == attempt.manifest.attempt_id
    assert sum("plan_series_generate" in item.name for item in attempts) == 1

    # The committed plan manifest must carry prompt/schema digests so that
    # immutable provenance is queryable (RUNTIME_ARTIFACT_RETENTION_REDESIGN §provenance).
    expected_prompt_digest = None
    expected_schema_digest = None
    for item in attempts:
        if "plan_series_generate" not in item.name:
            continue
        manifest_path = next(item.glob("artifacts/plan-series.json.manifest.json"))
        import json as _json

        manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_prompt_digest = manifest["prompt_digest"]
        expected_schema_digest = manifest["schema_digest"]
    assert expected_prompt_digest is not None
    assert expected_schema_digest is not None
    assert plan_ref.manifest.prompt_digest == expected_prompt_digest
    assert plan_ref.manifest.schema_digest == expected_schema_digest
