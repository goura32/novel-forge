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
