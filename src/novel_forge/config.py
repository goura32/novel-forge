"""Canonical runtime configuration for NovelForge.

The runtime deliberately reads one location only.  Keeping this policy here,
instead of at individual CLI call-sites, prevents workspace-local configuration
from changing a run after it has been selected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

try:
    import yaml
except ImportError:  # pragma: no cover - project dependency, defensive only
    yaml = None


class StrictConfigModel(BaseModel):
    """Reject misspelled or retired runtime settings instead of silently ignoring them."""

    model_config = ConfigDict(extra="forbid")


class WorkspaceConfig(StrictConfigModel):
    root: Path | None = None


class LLMConfig(StrictConfigModel):
    model: str = "qwen3.6:35b-a3b-mtp-q4_K_M"
    ollama_host: str = "ws1.local:11434"
    timeout_seconds: int = Field(default=3600, ge=1)
    ollama_options: dict[str, Any] = Field(
        default_factory=lambda: {
            "think": True,
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0,
        }
    )
    num_predict: int = Field(default=-1, description="-1 = unlimited output (risk of runaway generation)")
    num_ctx: int = Field(default=262144, description="context window in tokens")


class QualityConfig(StrictConfigModel):
    """Bounded retries for invalid LLM contract outputs, including the first call."""

    max_generation_attempts: int = Field(default=3, ge=1)


class NarrativeTopologyConfig(StrictConfigModel):
    """Production-scale structural bounds pinned into immutable PNCA requests."""

    min_chapters_per_volume: int = Field(default=10, ge=1)
    max_chapters_per_volume: int = Field(default=14, ge=1)
    min_scenes_per_chapter: int = Field(default=2, ge=1)
    max_scenes_per_chapter: int = Field(default=5, ge=1)
    min_scenes_per_volume: int = Field(default=32, ge=1)
    max_scenes_per_volume: int = Field(default=45, ge=1)
    max_five_scene_chapters_per_volume: int = Field(default=2, ge=0)

    @model_validator(mode="after")
    def _topology_bounds_are_ordered(self) -> NarrativeTopologyConfig:
        if self.min_chapters_per_volume > self.max_chapters_per_volume:
            raise ValueError("min_chapters_per_volume cannot exceed max_chapters_per_volume")
        if self.min_scenes_per_chapter > self.max_scenes_per_chapter:
            raise ValueError("min_scenes_per_chapter cannot exceed max_scenes_per_chapter")
        if self.min_scenes_per_volume > self.max_scenes_per_volume:
            raise ValueError("min_scenes_per_volume cannot exceed max_scenes_per_volume")
        return self


class LoggingConfig(StrictConfigModel):
    level: str = Field(default="DEBUG")


class RuntimeConfig(StrictConfigModel):
    """The destructive-redesign configuration contract.

    ``load`` accepts a path only for tests.  Production callers must use the
    no-argument form, which always resolves to ``Path.home()/.config`` and does
    not inspect XDG, the environment, a workspace, or the current directory.
    """

    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    quality: QualityConfig = Field(default_factory=QualityConfig)
    narrative: NarrativeTopologyConfig = Field(default_factory=NarrativeTopologyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    verbose: bool = False

    @classmethod
    def canonical_path(cls) -> Path:
        return Path.home() / ".config" / "novel-forge" / "config.yaml"

    @classmethod
    def load(cls, *, path: Path | None = None) -> RuntimeConfig:
        config_path = path if path is not None else cls.canonical_path()
        if not config_path.exists():
            return cls()
        if yaml is None:
            raise RuntimeError("PyYAML is required to read NovelForge configuration")
        try:
            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise RuntimeError(f"Cannot read runtime config: {config_path}") from exc
        except Exception as exc:
            raise ValueError(f"Invalid runtime config: {config_path}") from exc
        if loaded is None:
            return cls()
        if not isinstance(loaded, dict):
            raise ValueError(f"Runtime config must be a mapping: {config_path}")
        return cls.model_validate(loaded)

    def resolve_workdir(self, cli_workdir: Path | None) -> Path:
        if cli_workdir is not None:
            return cli_workdir.expanduser().resolve()
        if self.workspace.root is not None:
            return self.workspace.root.expanduser().resolve()
        raise ValueError(
            "作業フォルダが未設定です。\n"
            "config.yaml の workspace.root または --workdir を指定してください。"
        )
