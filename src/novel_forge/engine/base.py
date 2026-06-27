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
from typing import Any

from novel_forge.bible_manager import BibleManager
from novel_forge.context_builder import ContextBuilder
from novel_forge.llm_client import LLMClient, load_config
from novel_forge.logging_config import console, get_logger, setup_logging
from novel_forge.models import (
    ProjectState,
    SceneRecord,
    VolumeProgress,
)
from novel_forge.prompts import PromptManager
from novel_forge.quality_gate import QualityGate
from novel_forge.scene_writer import SceneWriter
from novel_forge.schemas import validate_schemas
from novel_forge.storage import BibleStorage, BlackboardStorage, StateStorage

_OLLAMA_OPTION_KEYS = [
    "temperature", "top_k", "top_p", "repeat_penalty",
    "presence_penalty", "frequency_penalty", "num_ctx",
    "num_predict", "seed", "stop", "tfs_z", "typical_p",
    "mirostat", "mirostat_tau", "mirostat_eta", "penalize_newline",
]


def _build_ollama_options(llm_cfg: dict) -> dict:
    """config.yaml から ollama options 辞書を構築する。"""
    options = dict(llm_cfg.get("ollama_options") or {})
    for key in _OLLAMA_OPTION_KEYS:
        if key in llm_cfg and llm_cfg[key] is not None:
            options[key] = llm_cfg[key]
    if "think" in llm_cfg:
        options["think"] = llm_cfg["think"]
    return options


def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID exists."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class NovelEngineBase:
    """Base class for NovelEngine — __init__, helpers, state management.

    This class holds all runtime state. Phase methods are provided by
    NovelEngine, which delegates to standalone functions.
    """

    _signal_cleanup: Any = None
    _BLOCKER = "致命的"
    _CRITICAL = "重大"
    _MAJOR = "重要"
    _DEFAULT_MODEL = "qwen3.6:35b-a3b-mtp-q4_K_M"
    _DEFAULT_NUM_PREDICT = -1
    _DEFAULT_NUM_CTX = 262144
    _DEFAULT_TIMEOUT = 3600
    _DEFAULT_MAX_RETRIES = 2

    def __init__(
        self,
        workdir: Path,
        model: str | None = None,
        lang: str = "ja",
        llm_client: LLMClient | None = None,
        prompt_manager: PromptManager | None = None,
        config: dict[str, Any] | None = None,
        max_review_retries: int | None = None,
        verbose: bool | None = None,
        raw_log_enabled: bool | None = None,
        phase: str = "",
    ):
        self._workdir = Path(workdir) if isinstance(workdir, str) else workdir
        self._lang = lang

        cfg = config if config is not None else load_config()

        log_cfg = cfg.get("logging", {})
        self._verbose = verbose if verbose is not None else log_cfg.get("verbose", False)
        self._raw_log_enabled = (
            raw_log_enabled if raw_log_enabled is not None else log_cfg.get("raw_log", False)
        )
        self._log_level = log_cfg.get("log_level", "DEBUG")
        self._slug = ""
        self._phase = phase
        self._strict = False

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
                print(f"[Schema Error] {err}")
            raise SystemExit(
                f"Schema validation failed — {len(schema_errors)} file(s) have errors."
            )

        self._log = get_logger("novel_forge.engine")
        self._storage = StateStorage(self._series_dir)
        self._bb_storage = BlackboardStorage(self._series_dir)
        self._bible_storage = BibleStorage(self._series_dir)

        lock_path = Path(workdir) / ".lock"
        if lock_path.exists():
            try:
                lock_pid = int(lock_path.read_text().strip())
                if not _is_process_alive(lock_pid):
                    lock_path.unlink(missing_ok=True)
                    console.print(f"[dim]⚠ Removed stale lock (PID={lock_pid}): {lock_path}[/dim]")
            except (ValueError, OSError):
                lock_path.unlink(missing_ok=True)
                console.print(f"[dim]⚠ Removed corrupted lock: {lock_path}[/dim]")

        if llm_client is None:
            llm_cfg = cfg.get("llm", {})
            model = model or self._DEFAULT_MODEL
            model = llm_cfg.get("model", model)
            if model is None:
                model = self._DEFAULT_MODEL
            timeout = llm_cfg.get("timeout_seconds", self._DEFAULT_TIMEOUT)
            max_retries = llm_cfg.get("max_retries", self._DEFAULT_MAX_RETRIES)
            num_predict = llm_cfg.get("num_predict", self._DEFAULT_NUM_PREDICT)
            num_ctx = llm_cfg.get("num_ctx", self._DEFAULT_NUM_CTX)
            host = llm_cfg.get("ollama_host", None)
            api_url = f"http://{host}/api/chat" if host else None
            vol = ""
            llm_client = LLMClient(
                api_url=api_url,
                model=model,
                raw_log_dir=Path(workdir) / "_raw_logs",
                raw_log_enabled=self._raw_log_enabled,
                phase=phase,
                timeout_seconds=timeout,
                max_retries=max_retries,
                num_predict=num_predict,
                num_ctx=num_ctx,
                ollama_options=_build_ollama_options(llm_cfg),
                series_slug=self._slug,
                volume=vol,
            )
        self._llm = llm_client
        self._prompts = prompt_manager or PromptManager()
        quality_retries = (
            max_review_retries
            if max_review_retries is not None
            else cfg.get("quality", {}).get("max_review_retries", QualityGate.DEFAULT_MAX_RETRIES)
        )
        self._quality = QualityGate(max_retries=quality_retries)
        self._state = self._storage.load()

        self._ctx_builder = ContextBuilder(self._series_dir, self._bb_storage, self._bible_storage)
        self._bible_mgr = BibleManager(self._bible_storage)
        self._scene_writer = SceneWriter(
            workdir,
            self._llm,
            self._prompts,
            self._quality,
            self._bb_storage,
            self._bible_storage,
            series_dir=self._series_dir,
        )

    @property
    def state(self) -> ProjectState:
        return self._state

    @property
    def workdir(self) -> Path:
        return self._workdir

    @property
    def _series_dir(self) -> Path:
        """Series output directory: {workdir}/{slug}/ (temp during plan)."""
        if hasattr(self, "_cached_series_dir"):
            return self._cached_series_dir
        if not self._slug:
            if not hasattr(self, "_tmp_dir"):
                self._tmp_dir = Path(tempfile.mkdtemp(prefix="novel-forge-"))
            self._cached_series_dir = self._tmp_dir
            return self._tmp_dir
        result = self._workdir / self._slug
        self._cached_series_dir = result
        return result

    def _move_to_final_dir(self) -> None:
        """Move temp directory contents to final {slug}/ directory."""
        if hasattr(self, "_tmp_dir") and self._tmp_dir.exists():
            final_dir = self._series_dir
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
        if hasattr(self, "_cached_series_dir"):
            del self._cached_series_dir

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
        return json.loads(path.read_text(encoding="utf-8"))

    def _get_or_create_scene_record(self, vol: VolumeProgress, scene_number: int) -> SceneRecord:
        for s in vol.scenes:
            if s.scene_number == scene_number:
                return s
        record = SceneRecord(scene_number=scene_number)
        vol.scenes.append(record)
        return record
