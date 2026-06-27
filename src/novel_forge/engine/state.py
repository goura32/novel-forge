"""Engine state — all runtime state in one place.

This replaces NovelEngineBase. Phase functions receive this as their
first argument instead of self, making dependencies visible and testable.
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
    options = dict(llm_cfg.get("ollama_options") or {})
    for key in _OLLAMA_OPTION_KEYS:
        if key in llm_cfg and llm_cfg[key] is not None:
            options[key] = llm_cfg[key]
    if "think" in llm_cfg:
        options["think"] = llm_cfg["think"]
    return options


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class EngineState:
    """Mutable state for all engine phases.

    Phase functions receive this as their first argument instead of self.
    """

    def __init__(
        self,
        workdir: Path,
        model: str | None = None,  # type: ignore[assignment]
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
        self._phase = phase
        self._strict = False

        cfg = config if config is not None else load_config()
        log_cfg = cfg.get("logging", {})
        self._verbose = verbose if verbose is not None else log_cfg.get("verbose", False)
        self._raw_log_enabled = (
            raw_log_enabled if raw_log_enabled is not None else log_cfg.get("raw_log", False)
        )
        self._log_level = log_cfg.get("log_level", "DEBUG")
        self._slug = ""

        # Logging
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

        # Lock check
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

        # LLM client
        if llm_client is None:
            llm_cfg = cfg.get("llm", {})
            default_model = "qwen3.6:35b-a3b-mtp-q4_K_M"
            model = model or llm_cfg.get("model") or default_model
            timeout = llm_cfg.get("timeout_seconds", 3600)
            max_retries = llm_cfg.get("max_retries", 2)
            num_predict = llm_cfg.get("num_predict", -1)
            num_ctx = llm_cfg.get("num_ctx", 262144)
            host = llm_cfg.get("ollama_host", None)
            api_url = f"http://{host}/api/chat" if host else None
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
                volume="",
            )
        self._llm = llm_client
        self._prompts = prompt_manager or PromptManager()

        quality_retries = (
            max_review_retries
            if max_review_retries is not None
            else cfg.get("quality", {}).get("max_review_retries", QualityGate.DEFAULT_MAX_RETRIES)
        )
        self._quality = QualityGate(max_retries=quality_retries)

        # Storage (lazy)
        self._storage: StateStorage | None = None
        self._bb_storage: BlackboardStorage | None = None
        self._bible_storage: BibleStorage | None = None
        self._ctx_builder: ContextBuilder | None = None
        self._bible_mgr: BibleManager | None = None
        self._scene_writer: SceneWriter | None = None

        # Load state
        self._state = self._storage_loaded_state()

    def _storage_loaded_state(self) -> ProjectState:
        return StateStorage(self._resolve_series_dir()).load()

    # -- Properties ------------------------------------------------------

    @property
    def workdir(self) -> Path:
        return self._workdir

    @property
    def slug(self) -> str:
        return self._slug

    @slug.setter
    def slug(self, value: str) -> None:
        self._slug = value
        self._cached_series_dir = None

    @property
    def lang(self) -> str:
        return self._lang

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def strict(self) -> bool:
        return self._strict

    @strict.setter
    def strict(self, value: bool) -> None:
        self._strict = value

    @property
    def status(self) -> str:
        return self._state.status

    @status.setter
    def status(self, value: str) -> None:
        self._state.status = value

    @property
    def volumes(self):
        return self._state.volumes

    @property
    def llm(self) -> LLMClient:
        return self._llm  # type: ignore[return-value]

    @property
    def prompts(self) -> PromptManager:
        return self._prompts

    @property
    def quality(self) -> QualityGate:
        return self._quality

    @property
    def log(self):
        return self._log

    @property
    def state(self) -> ProjectState:
        return self._state

    @property
    def _series_dir(self) -> Path:
        if not self._slug:
            if not hasattr(self, "_tmp_dir"):
                self._tmp_dir = Path(tempfile.mkdtemp(prefix="novel-forge-"))
            return self._tmp_dir
        return self._workdir / self._slug

    @_series_dir.setter
    def _series_dir(self, value: Path) -> None:
        pass  # No-op; managed internally

    def _resolve_series_dir(self) -> Path:
        if not self._slug:
            if not hasattr(self, "_tmp_dir"):
                self._tmp_dir = Path(tempfile.mkdtemp(prefix="novel-forge-"))
            return self._tmp_dir
        return self._workdir / self._slug

    # -- Storage (lazy init) -------------------------------------------

    @property
    def storage(self) -> StateStorage:
        if self._storage is None:
            self._storage = StateStorage(self._series_dir)
        return self._storage

    @property
    def bb_storage(self) -> BlackboardStorage:
        if self._bb_storage is None:
            self._bb_storage = BlackboardStorage(self._series_dir)
        return self._bb_storage

    @property
    def bible_storage(self) -> BibleStorage:
        if self._bible_storage is None:
            self._bible_storage = BibleStorage(self._series_dir)
        return self._bible_storage

    @property
    def ctx_builder(self) -> ContextBuilder:
        if self._ctx_builder is None:
            self._ctx_builder = ContextBuilder(
                self._series_dir, self.bb_storage, self.bible_storage
            )
        return self._ctx_builder

    @property
    def bible_mgr(self) -> BibleManager:
        if self._bible_mgr is None:
            self._bible_mgr = BibleManager(self.bible_storage)
        return self._bible_mgr

    @property
    def scene_writer(self) -> SceneWriter:
        if self._scene_writer is None:
            self._scene_writer = SceneWriter(
                self._workdir,
                self._llm,
                self._prompts,
                self._quality,
                self.bb_storage,
                self.bible_storage,
                series_dir=self._series_dir,
            )
        return self._scene_writer

    # -- State management -----------------------------------------------

    def save(self) -> None:
        self.storage.save(self._state)

    def move_to_final_dir(self) -> None:
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

    def current_volume(self) -> VolumeProgress:
        vol_num = self._state.current_volume
        for v in self._state.volumes:
            if v.volume_number == vol_num:
                return v
        vol = VolumeProgress(volume_number=vol_num)
        self._state.volumes.append(vol)
        return vol

    def get_or_create_scene_record(self, vol: VolumeProgress, scene_number: int) -> SceneRecord:
        for s in vol.scenes:
            if s.scene_number == scene_number:
                return s
        record = SceneRecord(scene_number=scene_number)
        vol.scenes.append(record)
        return record

    # -- File I/O -------------------------------------------------------

    def save_path(self, vol_num: int, filename: str, data: Any, version: int | None = None) -> None:
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

    def load_path(self, vol_num: int, filename: str) -> dict:
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

    # -- Slugify --------------------------------------------------------

    @staticmethod
    def slugify(title: str) -> str:
        import hashlib, re
        romaji_parts = re.findall(r"[a-zA-Z][a-zA-Z0-9]*", title)
        if romaji_parts:
            slug = "_".join(p.lower() for p in romaji_parts)
            slug = re.sub(r"[^a-z0-9_]", "", slug)
            if slug:
                return slug[:32]
        h = hashlib.md5(title.encode()).hexdigest()[:12]
        return f"series_{h}"
