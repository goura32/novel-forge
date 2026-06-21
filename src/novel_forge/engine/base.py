"""NovelEngine base — __init__, helpers, state management."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

from novel_forge.bible_manager import BibleManager
from novel_forge.context_builder import ContextBuilder
from novel_forge.models import (
    ProjectState,
    VolumeProgress,
    SceneRecord,
)
from novel_forge.llm_client import LLMClient, load_config
from novel_forge.prompts import PromptManager
from novel_forge.quality_gate import QualityGate
from novel_forge.schemas import get_schema
from novel_forge.scene_writer import SceneWriter
from novel_forge.storage import StateStorage, BlackboardStorage, BibleStorage
from novel_forge.logging_config import setup_logging, get_logger, console


class NovelEngineBase:
    """Base class for NovelEngine — __init__, helpers, state management."""

    def __init__(
        self,
        workdir: Path,
        model: str = "qwen3.6:35b-a3b-mtp-q4_K_M",
        lang: str = "ja",
        llm_client: LLMClient | None = None,
        prompt_manager: PromptManager | None = None,
        config: dict[str, Any] | None = None,
        max_review_retries: int | None = None,
        verbose: bool = False,
        raw_log_enabled: bool = False,
    ):
        self._workdir = workdir
        self._lang = lang
        self._verbose = verbose
        self._slug: str = ""
        self._raw_log_enabled = raw_log_enabled
        self._log = get_logger("novel_forge.engine")
        self._storage = StateStorage(self._series_dir)
        self._bb_storage = BlackboardStorage(self._series_dir)
        self._bible_storage = BibleStorage(self._series_dir)

        cfg = config if config is not None else load_config()
        if llm_client is None:
            llm_cfg = cfg.get("llm", {})
            model = llm_cfg.get("model", model)
            timeout = llm_cfg.get("timeout_seconds", 600)
            max_retries = llm_cfg.get("max_retries", 2)
            num_predict = llm_cfg.get("num_predict", 65536)
            num_ctx = llm_cfg.get("num_ctx", None)
            host = llm_cfg.get("ollama_host", None)
            api_url = None
            if host:
                api_url = f"http://{host}/api/generate"
            llm_client = LLMClient(
                api_url=api_url,
                model=model,
                raw_log_dir=self._series_dir / "raw_logs",
                raw_log_enabled=self._raw_log_enabled,
                timeout_seconds=timeout,
                max_retries=max_retries,
                num_predict=num_predict,
                num_ctx=num_ctx,
                ollama_options=llm_cfg.get("ollama_options"),
            )
        self._llm = llm_client
        self._prompts = prompt_manager or PromptManager()
        quality_retries = max_review_retries if max_review_retries is not None else cfg.get("quality", {}).get("max_review_retries", QualityGate.DEFAULT_MAX_RETRIES)
        self._quality = QualityGate(max_retries=quality_retries)
        self._state = self._storage.load()

        # Sub-components
        self._ctx_builder = ContextBuilder(self._series_dir, self._bb_storage, self._bible_storage)
        self._bible_mgr = BibleManager(self._bible_storage)
        self._scene_writer = SceneWriter(
            workdir, self._llm, self._prompts, self._quality,
            self._bb_storage, self._bible_storage,
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
        """Series output directory.
        During plan(): uses temp dir /tmp/novel-forge-{pid}/
        After plan(): uses {workdir}/{timestamp}_{slug}/
        If slug is not set, tries to find existing series dir in workdir."""
        if not self._slug:
            # Check if there's an existing series directory (from previous plan)
            existing = self._find_existing_series_dir()
            if existing:
                return existing
            # Before plan(): use temp directory
            if not hasattr(self, "_tmp_dir"):
                self._tmp_dir = Path(tempfile.mkdtemp(prefix="novel-forge-"))
            return self._tmp_dir
        # After plan(): use final directory
        folder_name = self._slug.replace("-", "_")
        return self._workdir / f"{self._timestamp}_{folder_name}"

    def _find_existing_series_dir(self) -> Path | None:
        """Find existing series directory in workdir (for commands after plan)."""
        # Check if workdir itself is the series directory
        if (self._workdir / "series_plan.json").exists():
            return self._workdir
        # Look for {timestamp}_{slug} pattern directories
        for d in sorted(self._workdir.iterdir(), reverse=True):
            if d.is_dir() and "_" in d.name and not d.name.startswith("."):
                # Check if it contains series_plan.json
                if (d / "series_plan.json").exists():
                    return d
        return None

    @property
    def _timestamp(self) -> str:
        """Timestamp for this engine instance (set once at init)."""
        if not hasattr(self, "_ts"):
            self._ts = time.strftime("%Y%m%d_%H%M%S")
        return self._ts

    def _move_to_final_dir(self) -> None:
        """Move temp directory contents to final {timestamp}_{slug}/ directory."""
        if hasattr(self, "_tmp_dir") and self._tmp_dir.exists():
            final_dir = self._series_dir
            if not final_dir.exists():
                shutil.move(str(self._tmp_dir), str(final_dir))
            else:
                # Merge: move files from temp to final
                for item in self._tmp_dir.iterdir():
                    dest = final_dir / item.name
                    if dest.exists():
                        # If dest exists, merge contents recursively
                        if item.is_dir() and dest.is_dir():
                            for sub_item in item.iterdir():
                                sub_dest = dest / sub_item.name
                                if not sub_dest.exists():
                                    shutil.move(str(sub_item), str(sub_dest))
                        # If dest is file and item is file, skip (keep existing)
                    else:
                        shutil.move(str(item), str(dest))
                # Remove temp dir recursively (in case any items couldn't be moved)
                shutil.rmtree(self._tmp_dir, ignore_errors=True)

    # ── helpers ───────────────────────────────────────────────────────

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

    def _save_path(self, vol_num: int, filename: str, data: Any, version: int | None = None) -> None:
        """Save data to path. If version is given, append _v{N} before extension."""
        if version is not None and version > 0:
            # Insert _v{N} before extension: design.json → design_v1.json
            stem = Path(filename).stem
            suffix = Path(filename).suffix
            filename = f"{stem}_v{version}{suffix}"
        if vol_num == 0:
            path = self._series_dir / filename
        else:
            path = self._series_dir / f"vol{vol_num:02d}" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            json.dumps(data, ensure_ascii=False, indent=2)
            if isinstance(data, dict)
            else str(data)
        )
        path.write_text(content, encoding="utf-8")

    def _save_review(self, review_dir: Path, name: str, data: Any, version: int | None = None) -> None:
        """レビュー結果を review/ ディレクトリに保存する。"""
        review_dir.mkdir(parents=True, exist_ok=True)
        if version is not None and version > 0:
            name = f"{name}_v{version}"
        path = review_dir / f"{name}.json"
        content = json.dumps(data, ensure_ascii=False, indent=2)
        path.write_text(content, encoding="utf-8")

    def _load_path(self, vol_num: int, filename: str) -> dict:
        path = self._series_dir / f"vol{vol_num:02d}" / filename
        if not path.exists():
            # Try to find existing series directory
            existing = self._find_existing_series_dir()
            if existing:
                path = existing / f"vol{vol_num:02d}" / filename
        if not path.exists():
            raise FileNotFoundError(
                f"File not found: {path}\n"
                f"series_dir: {self._series_dir}\n"
                f"workdir: {self._workdir}"
            )
        return json.loads(path.read_text(encoding="utf-8"))

    def _get_or_create_scene_record(
        self, vol: VolumeProgress, scene_number: int
    ) -> SceneRecord:
        for s in vol.scenes:
            if s.scene_number == scene_number:
                return s
        record = SceneRecord(scene_number=scene_number)
        vol.scenes.append(record)
        return record

    def _ensure_config(self) -> None:
        """Generate config.yaml from template if it doesn't exist in workdir."""
        config_path = self._workdir / "config.yaml"
        if config_path.exists():
            return
        # Look for template in project root (parent of src/)
        template = Path(__file__).resolve().parent.parent.parent / "config.yaml"
        if template.exists():
            shutil.copy2(template, config_path)
            return
        # Fallback: create minimal config with defaults
        default_config = {
            "llm": {
                "model": "qwen3.6:35b-a3b-mtp-q4_K_M",
                "num_predict": 16384,
                "num_ctx": 65536,
                "timeout_seconds": 3600,
                "max_retries": 2,
                "ollama_options": {
                    "temperature": 0.7,
                    "top_k": 20,
                    "top_p": 0.80,
                    "repeat_penalty": 1.0,
                    "presence_penalty": 1.5,
                },
            },
            "quality": {
                "max_review_retries": 2,
            },
        }
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
        except Exception:
            pass  # Non-critical: engine works with code defaults

    def _review_and_revise(
        self,
        item: dict,
        review_fn,
        revise_fn,
        system: str,
        max_retries: int = 3,
        label: str = "",
    ) -> dict:
        """Generic review → revise loop.

        Args:
            item: The object to review/revise (modified in place).
            review_fn: Callable(item, system) -> review dict.
            revise_fn: Callable(item, review, system) -> revised item dict.
            system: System prompt string.
            max_retries: Maximum number of review/revise cycles.
            label: Label for stderr logging.
        """
        review = review_fn(item, system)
        for retry in range(max_retries):
            blocker_issues = [i for i in review.get("issues", []) if i.get("severity") == "致命的"]
            critical_issues = [i for i in review.get("issues", []) if i.get("severity") == "重大"]
            major_issues = [i for i in review.get("issues", []) if i.get("severity") == "重要"]
            revision_needed = len(blocker_issues) > 0 or len(critical_issues) > 0 or len(major_issues) >= 2
            if not revision_needed:
                break
            self._log.warning(
                "  [%s] blocker=%d critical=%d major=%d retry=%d/%d",
                label, len(blocker_issues), len(critical_issues), len(major_issues),
                retry + 1, max_retries,
            )
            item = revise_fn(item, review, system)
            review = review_fn(item, system)
        return item
