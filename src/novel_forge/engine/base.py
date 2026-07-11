"""NovelEngine base — __init__, helpers, state management.

NovelEngine holds all runtime state (LLM, storage, prompts, quality).
Phase methods (plan, design, write, export) are provided by NovelEngine,
which delegates to standalone functions in plan.py, design.py, etc.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, cast

from novel_forge.llm_client import LLMClient, _build_ollama_options, load_config
from novel_forge.logging_config import console, get_logger, setup_logging
from novel_forge.models import (
    ProjectState,
    SceneRecord,
    VolumeProgress,
)
from novel_forge.prompts import PromptManager
from novel_forge.quality_gate import QualityGate
from novel_forge.runtime import (
    AttemptCapture,
    RunHandle,
    RunLock,
    RunManager,
    RunRepository,
)
from novel_forge.schemas import validate_schemas
from novel_forge.storage import StateStorage
from novel_forge.task_registry import DEFAULT_TASK_REGISTRY


def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID exists."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _load_config_for_workdir(workdir: Path) -> dict[str, Any]:
    """Load config with runtime precedence: env path > workdir/parent config > cwd search."""
    env_path = os.environ.get("NOVEL_FORGE_CONFIG")
    if env_path:
        return load_config(Path(env_path))

    workdir_path = Path(workdir)
    candidates = []
    if (workdir_path / "series_plan.json").exists():
        candidates.append(workdir_path.parent / "config.yaml")
    candidates.append(workdir_path / "config.yaml")

    for candidate in candidates:
        if candidate.exists():
            return load_config(candidate)

    return load_config()


class NovelEngineBase:
    """Base class for NovelEngine — __init__, helpers, state management.

    This class holds all runtime state. Phase methods are provided by
    NovelEngine, which delegates to standalone functions.
    """

    _signal_cleanup: Any = None
    _DEFAULT_MODEL = "qwen3.6:35b-a3b-mtp-q4_K_M"
    _DEFAULT_NUM_PREDICT = -1
    _DEFAULT_NUM_CTX = 262144
    _DEFAULT_TIMEOUT = 3600
    _DEFAULT_MAX_RETRIES = 2
    _DEFAULT_MAX_GENERATION_COUNT = 4
    _DEFAULT_MAX_REVIEW_COUNT = 3

    def __init__(
        self,
        workdir: Path,
        model: str | None = None,
        lang: str = "ja",
        llm_client: LLMClient | None = None,
        prompt_manager: PromptManager | None = None,
        config: dict[str, Any] | None = None,
        max_review_count: int | None = None,
        max_generation_count: int | None = None,
        verbose: bool | None = None,
        phase: str = "",
        # -- Dependency injection for testing --
        storage: StateStorage | None = None,
        # -- Destructive runtime redesign --
        run: RunHandle | None = None,
        repository: RunRepository | None = None,
        manager: RunManager | None = None,
        workspace_lock: RunLock | None = None,
    ):
        self._workdir = Path(workdir) if isinstance(workdir, str) else workdir
        self._lang = lang

        cfg = config if config is not None else _load_config_for_workdir(self._workdir)

        log_cfg = cfg.get("logging", {})
        self._verbose = verbose if verbose is not None else log_cfg.get("verbose", False)
        self._log_level = log_cfg.get("log_level", "DEBUG")
        # If workdir is an existing series directory (contains series_plan.json),
        # use it directly as _series_dir and derive slug from it.
        workdir_path = Path(workdir) if isinstance(workdir, str) else workdir
        if (workdir_path / "series_plan.json").exists():
            self._slug = workdir_path.name
            self.__dict__["_cached_series_dir"] = workdir_path
        else:
            self._slug = ""
        self._phase = phase
        self._strict = True

        # ログは全シリーズ共通で config.yaml と同じフォルダに出力
        log_dir = Path(workdir)
        log_slug = ""
        if (log_dir / "series_plan.json").exists():
            log_dir = log_dir.parent
            log_slug = workdir.name
        log_file = log_dir / "novel_forge.log"
        setup_logging(
            log_file=log_file,
            verbose=self._verbose,
            log_level=self._log_level,
            series_slug=log_slug,
        )

        schema_errors = validate_schemas()
        if schema_errors:
            for err in schema_errors:
                console.print(f"[red]Schema Error: {err}[/red]")
            raise SystemExit(
                f"Schema validation failed — {len(schema_errors)} file(s) have errors."
            )

        self._log = get_logger("novel_forge.engine")
        self._storage = storage or StateStorage(self._series_dir)
        # v1 legacy collaborators (BibleManager / BibleStorage / Blackboard /
        # ContextBuilder / SceneWriter) are intentionally NOT instantiated here.
        # The v2 pipeline (plan → design → write → export) is the single source
        # of truth and never reads/writes the legacy bible.json or blackboard.

        if llm_client is None:
            llm_cfg = cfg.get("llm", {})
            model = model if model is not None else llm_cfg.get("model") or self._DEFAULT_MODEL
            timeout = llm_cfg.get("timeout_seconds", self._DEFAULT_TIMEOUT)
            transport_retries = llm_cfg.get("transport_retries", llm_cfg.get("max_retries", self._DEFAULT_MAX_RETRIES))
            num_predict = llm_cfg.get("num_predict", self._DEFAULT_NUM_PREDICT)
            num_ctx = llm_cfg.get("num_ctx", self._DEFAULT_NUM_CTX)
            host = llm_cfg.get("ollama_host", None)
            api_url = f"http://{host}/api/chat" if host else None
            vol = ""
            llm_client = LLMClient(
                api_url=api_url,
                model=model,
                raw_log_dir=Path(workdir) / "_raw_logs" if self._verbose else None,
                phase=phase,
                timeout_seconds=timeout,
                transport_retries=transport_retries,
                num_predict=num_predict,
                num_ctx=num_ctx,
                ollama_options=_build_ollama_options(llm_cfg),
                series_slug=self._slug,
                volume=vol,
            )
        self._run = run
        self._repository = repository
        self._manager = manager
        self._workspace_lock = workspace_lock
        self._attempt: Any = None
        self._capture: AttemptCapture | None = None
        self._llm = llm_client
        self._prompts = prompt_manager or PromptManager()
        quality_cfg = cfg.get("quality", {})
        review_retries = (
            max_review_count
            if max_review_count is not None
            else quality_cfg.get("max_review_count", self._DEFAULT_MAX_REVIEW_COUNT)
        )
        generation_retries = (
            max_generation_count
            if max_generation_count is not None
            else quality_cfg.get("max_generation_count", self._DEFAULT_MAX_GENERATION_COUNT)
        )
        self._quality = QualityGate(
            max_retries=review_retries,
            generation_count=generation_retries,
            review_count=review_retries,
        )
        self._state = self._storage.load()

        # v1 legacy collaborators are intentionally NOT instantiated here.
        # The v2 pipeline (plan → design → write → export) is the single
        # source of truth and uses the canon/ event store instead.

    @property
    def state(self) -> ProjectState:
        return self._state

    @property
    def workdir(self) -> Path:
        return self._workdir

    @property
    def _series_dir(self) -> Path:
        """Series output directory: {workdir}/{slug}/ (temp during plan)."""
        cached = self.__dict__.get("_cached_series_dir")
        if cached is not None:
            return cast(Path, cached)
        if not self._slug:
            if not hasattr(self, "_tmp_dir"):
                self._tmp_dir = Path(tempfile.mkdtemp(prefix="novel-forge-"))
            self.__dict__["_cached_series_dir"] = self._tmp_dir
            return self._tmp_dir
        result = self._workdir / self._slug
        self.__dict__["_cached_series_dir"] = result
        return result

    def _move_to_final_dir(self) -> None:
        """Move temp directory contents to final {slug}/ directory."""
        if hasattr(self, "_tmp_dir") and self._tmp_dir.exists():
            final_dir = self._workdir / self._slug
            if not final_dir.exists():
                shutil.move(str(self._tmp_dir), str(final_dir))
            else:
                for item in self._tmp_dir.iterdir():
                    dest = final_dir / item.name
                    if dest.exists():
                        if item.is_dir() and dest.is_dir():
                            for sub_item in item.iterdir():
                                sub_dest = dest / sub_item.name
                                if not sub_dest.exists():
                                    shutil.move(str(sub_item), str(sub_dest))
                    else:
                        shutil.move(str(item), str(dest))
                shutil.rmtree(self._tmp_dir, ignore_errors=True)
            self._log.info(f"Moved to final dir: {final_dir}")
        if "_cached_series_dir" in self.__dict__:
            del self.__dict__["_cached_series_dir"]
        self.__dict__["_cached_series_dir"] = self._workdir / self._slug
        self._rebind_series_dir()

    def _rebind_series_dir(self) -> None:
        """Rebind path-dependent collaborators after the series slug is known."""
        series_dir = self._series_dir
        self._storage = StateStorage(series_dir)
        # v1 legacy collaborators are intentionally NOT rebound here.  The v2
        # pipeline uses the canon/ event store (CanonEventStore) instead.

    def _save(self) -> None:
        self._storage.save(self._state)

    def _current_volume(self) -> VolumeProgress:
        vol_num = self._state.current_volume
        for v in self._state.volumes:
            if v.volume_number == vol_num:
                return v
        vol = VolumeProgress(volume_number=vol_num)
        self._state.volumes.append(vol)
        return vol

    def _save_path(
        self, vol_num: int, filename: str, data: Any, version: int | None = None
    ) -> None:
        """Save data to path. If version > 0, append _v{N} before extension."""
        if version is not None and version > 0:
            stem = Path(filename).stem
            suffix = Path(filename).suffix
            filename = f"{stem}_v{version}{suffix}"
        if vol_num == 0:
            path = self._series_dir / filename
        else:
            path = self._series_dir / f"vol{vol_num:02d}" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            json.dumps(data, ensure_ascii=False, indent=2) if isinstance(data, dict) else str(data)
        )
        path.write_text(content, encoding="utf-8")

    def _load_path(self, vol_num: int, filename: str) -> dict:
        path = self._series_dir / f"vol{vol_num:02d}" / filename
        if not path.exists():
            for d in sorted(self._workdir.iterdir(), reverse=True):
                if d.is_dir() and (d / "series_plan.json").exists():
                    path = d / f"vol{vol_num:02d}" / filename
                    if path.exists():
                        break
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return cast(dict[str, Any], data)

    def _load_series_plan(self) -> dict[str, Any]:
        """Load the series plan, preferring the runtime artifact when present.

        The redesign commits the series plan to the immutable runtime repository
        rather than writing a flat ``series_plan.json``.  Fall back to the flat
        file only for legacy / non-runtime callers.
        """
        repo = getattr(self, "_repository", None)
        slug = getattr(self, "_slug", None)
        if repo is not None and slug:
            try:
                ref = repo.latest_ready_artifact(slug, "plan", "series_plan")
                if ref is not None:
                    payload = repo.read_payload(ref)
                    if isinstance(payload, dict):
                        return payload
            except Exception as exc:  # pragma: no cover - defensive
                self._log.debug("runtime series_plan lookup failed, falling back: %s", exc)
        flat = self._series_dir / "series_plan.json"
        if flat.exists():
            try:
                return cast(dict[str, Any], json.loads(flat.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                return {}
        return {}

    def _get_or_create_scene_record(self, vol: VolumeProgress, scene_number: int) -> SceneRecord:
        for s in vol.scenes:
            if s.scene_number == scene_number:
                return s
        record = SceneRecord(scene_number=scene_number)
        vol.scenes.append(record)
        return record


    def _existing_slugs(self) -> set[str]:
        """Slugs of series that already have a runtime ledger."""
        if self._repository is None:
            return set()
        slugs: set[str] = set()
        for child in sorted(self._workdir.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if (self._repository.series_runtime_root(child.name) / "ledger").exists():
                slugs.add(child.name)
        return slugs
    def _begin_attempt(self, task_id: str, reason: str, *, retry_number: int = 1, seed: int | None = None):
        """Start (or resume) an immutable attempt scoped to the active run."""
        if self._repository is None or self._run is None:
            raise RuntimeError("runtime repository is not configured for this engine")
        self._attempt = self._repository.start_attempt(
            self._run,
            task_id=task_id,
            phase=self._phase,
            reason=reason,
            retry_number=retry_number,
            seed=seed,
        )
        self._capture = AttemptCapture(self._repository, self._attempt, self._verbose)
        if self._llm is not None:
            self._llm._capture = self._capture
        return self._attempt

    def _commit_artifact(self, *, artifact_type: str, logical_key: str, payload: object, payload_name: str, **kwargs):
        """Commit a ready artifact for the active attempt and return its id."""
        if self._repository is None or self._attempt is None:
            raise RuntimeError("no active attempt to commit")
        ref = self._repository.commit_artifact(
            self._attempt,
            artifact_type=artifact_type,
            logical_key=logical_key,
            payload=payload,
            payload_name=payload_name,
            **kwargs,
        )
        return ref

    def _fail_attempt(self, *, error_code: str, retryable: bool, http_status: int | None = None, detail: str | None = None) -> None:
        if self._repository is None or self._attempt is None:
            raise RuntimeError("no active attempt to fail")
        self._repository.fail_attempt(
            self._attempt,
            error_code=error_code,
            retryable=retryable,
            http_status=http_status,
            detail=detail,
        )

    def _require_task(self, task_id: str):
        return DEFAULT_TASK_REGISTRY.get(task_id)

    def _slug_exists(self, slug: str) -> bool:
        if self._repository is None:
            return False
        return (self._repository.series_runtime_root(slug) / "ledger").exists()

    def _promote_series_lock(self, slug: str):
        if self._repository is None or self._manager is None or self._run is None or self._workspace_lock is None:
            return
        self._manager.promote_plan_to_series(workspace_lock=self._workspace_lock, run=self._run, slug=slug)

    def _create_selection_snapshot(self, *, slug: str, slots: dict[str, str], reason: str, base_snapshot_id: str | None = None):
        if self._repository is None:
            raise RuntimeError("runtime repository is not configured")
        return self._repository.create_selection_snapshot(slug=slug, slots=slots, reason=reason, base_snapshot_id=base_snapshot_id)
