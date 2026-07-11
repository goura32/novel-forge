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
# The legacy mutable NovelEngine no longer exists.  Tests build RunRepository /
# RunHandle / RunManager directly (or use RuntimeWorkflow) so that
# _begin_attempt / _commit_artifact record immutable artifacts.
# ---------------------------------------------------------------------------
from novel_forge.runtime import RunHandle, RunLock, RunManager, RunRepository  # noqa: E402


def make_test_repository(workdir: Path) -> tuple[RunRepository, RunManager, RunHandle, RunLock]:
    """Create an isolated runtime for a test workdir and return its handles."""
    repo = RunRepository(workdir)
    manager = RunManager(repo)
    run = repo.create_run(
        command="plan",
        model="test-model",
        verbose=False,
    )
    lock = manager.acquire(scope="series", run=run, phase="test")
    return repo, manager, run, lock
