"""Canonical runtime configuration for NovelForge.

The runtime deliberately reads one location only.  Keeping this policy here,
instead of at individual CLI call-sites, prevents workspace-local configuration
from changing a run after it has been selected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

try:
    import yaml
except ImportError:  # pragma: no cover - project dependency, defensive only
    yaml = None


class WorkspaceConfig(BaseModel):
    root: Path | None = None


class LLMConfig(BaseModel):
    model: str = "qwen3.6:35b-a3b-mtp-q4_K_M"
    ollama_host: str = "ws1.local:11434"
    timeout_seconds: int = Field(default=3600, ge=1)
    transport_retries: int = Field(default=2, ge=0)
    ollama_options: dict[str, Any] = Field(default_factory=lambda: {"think": False})


class QualityConfig(BaseModel):
    max_generation_count: int = Field(default=4, ge=1)
    max_review_count: int = Field(default=3, ge=1)
    max_summary_review_count: int = Field(default=2, ge=1)


class RuntimeConfig(BaseModel):
    """The destructive-redesign configuration contract.

    ``load`` accepts a path only for tests.  Production callers must use the
    no-argument form, which always resolves to ``Path.home()/.config`` and does
    not inspect XDG, the environment, a workspace, or the current directory.
    """

    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    quality: QualityConfig = Field(default_factory=QualityConfig)
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
