"""Infrastructure: locks, engine factory, series resolution."""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from rich.console import Console
from rich.table import Table

from novel_forge.engine import NovelEngine
from novel_forge.llm_client import load_config

console = Console()

DEFAULT_MODEL = "qwen3.6:35b-a3b-mtp-q4_K_M"
_LOCK_FILE_NAME = ".lock"
_STATE_FILE_NAME = ".novel_forge_state"
_LOCK_TIMEOUT_SECONDS = 300


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
    resolved_model = model if model is not None else llm_cfg.get("model") or DEFAULT_MODEL
    resolved_host = (
        ollama_host
        if ollama_host is not None
        else llm_cfg.get("ollama_host") or os.environ.get("OLLAMA_HOST", "ws1.local:11434")
    )
    return resolved_model, resolved_host


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _acquire_lock(series_dir: Path, timeout: float = _LOCK_TIMEOUT_SECONDS) -> Path:
    """Acquire exclusive lock. Overwrites stale locks immediately."""
    lock_path = series_dir / _LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Check stale lock
    if lock_path.exists():
        try:
            lock_pid = int(lock_path.read_text().strip())
        except (ValueError, OSError):
            lock_pid = 0
        if lock_pid <= 0 or not _is_process_alive(lock_pid):
            console.print(f"[yellow]⚠ Stale lock (PID={lock_pid}) detected, removing.[/yellow]")
            lock_path.unlink(missing_ok=True)

    deadline = time.monotonic() + timeout
    last_msg = time.monotonic()
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
                os.close(fd)
            return lock_path
        except FileExistsError:
            try:
                lock_pid = int(lock_path.read_text().strip())
            except (ValueError, OSError):
                lock_pid = 0
            if lock_pid > 0 and _is_process_alive(lock_pid):
                if time.monotonic() >= deadline:
                    console.print(
                        f"[red]✗ Lock held by PID={lock_pid} (waited {timeout:.0f}s). "
                        f"Another process is running on this series.[/red]"
                    )
                    sys.exit(1)
                now = time.monotonic()
                if now - last_msg >= 5.0:
                    waited = now - (deadline - timeout)
                    console.print(
                        f"[dim]⏳ Waiting for lock (PID={lock_pid}, waited {waited:.0f}s)...[/dim]"
                    )
                    last_msg = now
                time.sleep(0.5)
            else:
                lock_path.unlink(missing_ok=True)


def _release_lock(lock_path: Path) -> None:
    with contextlib.suppress(OSError):
        lock_path.unlink(missing_ok=True)


@contextmanager
def _series_lock(series_dir: Path) -> Generator[None]:
    lock_path = _acquire_lock(series_dir)
    try:
        yield
    finally:
        _release_lock(lock_path)


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
    raw_log: bool | None = None,
    phase: str = "",
    series: str = "",
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
        raw_log_enabled=raw_log,
        phase=phase,
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
        state_path = engine._series_dir / _STATE_FILE_NAME
        state = {
            "step": "interrupted",
            "status": f"interrupted_by_{sig_name}",
            "model": model,
            "lang": lang,
            "pid": os.getpid(),
            "updated_at": time.time(),
        }
        with contextlib.suppress(Exception):
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    original_sigterm = signal.signal(signal.SIGTERM, _signal_handler)
    original_sigint = signal.signal(signal.SIGINT, _signal_handler)
    engine._signal_cleanup = (original_sigterm, original_sigint)
    return engine


def make_series_lock(series_dir: Path):
    """Return context manager for series lock."""
    return _series_lock(series_dir)


def cmd_status(engine: NovelEngine) -> None:
    """Display status table."""
    s = engine.status()
    table = Table(title="NovelForge Status")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    for k, v in s.items():
        table.add_row(k, str(v))
    lock_path = engine._series_dir / _LOCK_FILE_NAME
    if lock_path.exists():
        try:
            lock_pid = int(lock_path.read_text().strip())
            age = time.time() - lock_path.stat().st_mtime
            if _is_process_alive(lock_pid):
                table.add_row(f"[bold]🔒 lock: PID={lock_pid} (active, {age:.0f}s ago)[/bold]", "")
            else:
                table.add_row(f"[dim]🔒 lock: PID={lock_pid} (stale, {age:.0f}s ago)[/dim]", "")
        except (ValueError, OSError):
            table.add_row("[dim]🔒 lock: corrupted[/dim]", "")
    console.print(table)


def cmd_doctor(
    model: str = DEFAULT_MODEL,
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