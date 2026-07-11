import sys
from pathlib import Path

# Ensure the repository root (containing the `tests` package) is importable so
# intra-test `from tests.test_v2_pipeline_e2e import ...` works under pytest.
ROOT = Path(__file__).resolve().parent.parent
# Also expose the `tests` directory itself so `from fixtures import ...` and
# `from fakes import ...` (packages living under tests/) resolve at top level.
TESTS = Path(__file__).resolve().parent
for d in (str(ROOT), str(TESTS)):
    if d not in sys.path:
        sys.path.insert(0, d)


# ---------------------------------------------------------------------------
# Destructive-redesign runtime bootstrap for tests.
#
# The engine no longer owns a mutable state file.  Tests must provide a
# RunRepository / RunHandle so that _begin_attempt / _commit_artifact can
# record immutable artifacts.  Use `engine_with_runtime` (or build one in a
# test-local fixture via the helpers below).
# ---------------------------------------------------------------------------
from novel_forge.runtime import RunHandle, RunLock, RunManager, RunRepository  # noqa: E402


def make_test_repository(workdir: Path) -> tuple[RunRepository, RunManager, RunHandle, RunLock]:
    """Create an isolated runtime for a test workdir and return its handles."""
    repo = RunRepository(workdir)
    manager = RunManager(repo)
    run = repo.create_run(
        command="test",
        model="test-model",
        verbose=False,
    )
    lock = manager.acquire(scope="series", run=run, phase="test")
    return repo, manager, run, lock


def engine_with_runtime(workdir: Path, llm_client, *, config: dict | None = None, **kwargs):
    """Build a NovelEngine wired to a fresh immutable runtime."""
    from novel_forge.engine import NovelEngine
    from novel_forge.prompts import PromptManager

    repo, manager, run, lock = make_test_repository(workdir)
    prompts = PromptManager(prompt_dir=workdir / "prompts")
    eng = NovelEngine(
        workdir=workdir,
        model="test-model",
        llm_client=llm_client,
        prompt_manager=prompts,
        config=config
        or {
            "llm": {"model": "test-model", "timeout_seconds": 10, "max_retries": 3},
            "quality": {"max_generation_count": 3, "max_review_count": 3},
        },
        run=run,
        repository=repo,
        manager=manager,
        workspace_lock=lock,
        **kwargs,
    )
    return eng
