"""Infrastructure: locks, engine factory, series resolution."""

from __future__ import annotations

import os
import re
import signal
from pathlib import Path

from rich.console import Console
from rich.table import Table

from novel_forge.config import RuntimeConfig
from novel_forge.engine import NovelEngine
from novel_forge.llm_client import load_config
from novel_forge.runtime import RunHandle, RunLock, RunManager, RunRepository

console = Console()
def _load_config_for_workdir(workdir: Path) -> dict:
    """Load config with runtime precedence: env path > workdir config > cwd search."""
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


def _resolve_doctor_defaults(
    workdir: Path,
    model: str | None,
    ollama_host: str | None,
) -> tuple[str, str]:
    """Resolve doctor options with CLI > config > built-in/env precedence."""
    cfg = _load_config_for_workdir(workdir)
    llm_cfg = cfg.get("llm", {})
    resolved_model = model if model is not None else llm_cfg.get("model") or RuntimeConfig().llm.model
    resolved_host = (
        ollama_host
        if ollama_host is not None
        else llm_cfg.get("ollama_host") or os.environ.get("OLLAMA_HOST", "ws1.local:11434")
    )
    return resolved_model, resolved_host


def _is_process_alive(pid: int) -> bool:
    """Alive check used by PID-identity lock helpers."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

def _find_existing_series(workdir: Path, slug: str | None = None) -> Path:
    """Find existing series directory."""
    if slug:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", slug):
            raise ValueError(f"Unsafe series slug: {slug}")
        root = workdir.resolve()
        series_dir = (workdir / slug).resolve()
        if series_dir != root and root not in series_dir.parents:
            raise ValueError(f"Unsafe series slug: {slug}")
        if not series_dir.exists():
            raise FileNotFoundError(f"Series '{slug}' not found in {workdir}")
        return series_dir
    if (workdir / "series_plan.json").exists():
        return workdir
    for d in sorted(workdir.iterdir(), reverse=True):
        if d.is_dir() and not d.name.startswith(".") and (d / "series_plan.json").exists():
            return d
    return workdir


def make_engine(
    workdir: Path = Path("."),
    model: str | None = None,
    lang: str = "ja",
    max_generation_count: int | None = None,
    max_review_count: int | None = None,
    verbose: bool | None = None,
    phase: str = "",
    series: str = "",
    run: RunHandle | None = None,
    repository: RunRepository | None = None,
    manager: RunManager | None = None,
    workspace_lock: RunLock | None = None,
) -> NovelEngine:
    """Create NovelEngine with signal handlers registered."""
    if series:
        workdir = workdir / series
    engine = NovelEngine(
        workdir=workdir,
        model=model,
        lang=lang,
        max_review_count=max_review_count,
        max_generation_count=max_generation_count,
        verbose=verbose,
        phase=phase,
        run=run,
        repository=repository,
        manager=manager,
        workspace_lock=workspace_lock,
    )

    _shutdown_requested = False

    def _signal_handler(signum, frame):
        nonlocal _shutdown_requested
        _shutdown_requested = True
        sig_name = signal.Signals(signum).name
        engine._log.warning(f"Received {sig_name} — shutting down after current step")
        console.print(
            f"\n[yellow]⚠ Received {sig_name} — shutting down after current step...[/yellow]"
        )
        if run is not None and repository is not None:
            repository._append_run_event(
                run.path,
                "run.interrupted",
                {"signal": sig_name, "pid": os.getpid()},
            )

    original_sigterm = signal.signal(signal.SIGTERM, _signal_handler)
    original_sigint = signal.signal(signal.SIGINT, _signal_handler)
    engine._signal_cleanup = (original_sigterm, original_sigint)
    return engine


def cmd_status(engine: NovelEngine) -> None:
    """Display status table."""
    s = engine.status()
    table = Table(title="NovelForge Status")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    for k, v in s.items():
        table.add_row(k, str(v))
    console.print(table)


def cmd_doctor(
    model: str = RuntimeConfig().llm.model,
    ollama_host: str = "ws1.local:11434",
) -> None:
    """Diagnose Ollama connectivity and model readiness."""
    import httpx as _httpx

    console.print("[bold]NovelForge Doctor[/bold]\n")

    # 1. Ollama connectivity
    console.print("1. Ollama connectivity")
    try:
        resp = _httpx.get(f"http://{ollama_host}/", timeout=5)
        console.print(
            "   [green]✓ Ollama is running[/green]"
            if resp.status_code == 200
            else f"   [red]✗ Status {resp.status_code}[/red]"
        )
    except Exception as e:
        console.print(f"   [red]✗ Cannot reach Ollama: {e}[/red]\n")
        return

    # 2. Model
    print(f"\n2. Model: {model}")
    try:
        resp = _httpx.post(f"http://{ollama_host}/api/show", json={"name": model}, timeout=15)
        if resp.status_code == 200:
            details = resp.json().get("details", {})
            print("   [green]✓ Model loaded[/green]")
            print(f"   context_length: {details.get('context_length', '?')}")
            print(f"   format: {details.get('format', '?')}")
        else:
            print(f"   [yellow]⚠ Status {resp.status_code}[/yellow]")
            print(f"   Run: ollama pull {model}")
    except Exception as e:
        print(f"   [red]✗ Check failed: {e}[/red]")

    print("\n[bold]Done.[/bold]")