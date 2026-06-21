from __future__ import annotations

import os
import signal
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

import typer
from rich.console import Console
from rich.table import Table

from novel_forge.engine import NovelEngine

app = typer.Typer(help="NovelForge — Local-LLM novel production pipeline")
console = Console()

DEFAULT_MODEL = "qwen3.6:35b-a3b-mtp-q4_K_M"
_LOCK_FILE_NAME = ".lock"
_STATE_FILE_NAME = ".novel_forge_state"
_LOCK_TIMEOUT_SECONDS = 300  # 5 min stale lock threshold


def _acquire_lock(series_dir: Path, timeout: float = 10.0) -> Path:
    """Acquire an exclusive lock for a series directory.

    Uses a .lock file containing the current PID. If a stale lock is detected
    (process no longer alive, or lock older than _LOCK_TIMEOUT_SECONDS), it is
    overwritten. Otherwise, raises an error immediately.

    Caller is responsible for releasing the lock via _release_lock().
    """
    lock_path = series_dir / _LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            # O_CREAT | O_EXCL ensures atomic creation
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
                os.close(fd)
            return lock_path
        except FileExistsError:
            # Check if the lock holder is still alive
            try:
                lock_pid = int(lock_path.read_text().strip())
            except (ValueError, OSError):
                lock_pid = 0
            if lock_pid <= 0 or not _is_process_alive(lock_pid):
                console.print(f"[yellow]⚠ Stale lock (PID={lock_pid}) detected, removing.[/yellow]")
                lock_path.unlink(missing_ok=True)
                continue
            # Check age — if too old, treat as stale
            try:
                mtime = lock_path.stat().st_mtime
                age = time.time() - mtime
            except OSError:
                age = 0
            if age > _LOCK_TIMEOUT_SECONDS:
                console.print(f"[yellow]⚠ Lock age {age:.0f}s > {_LOCK_TIMEOUT_SECONDS}s, removing.[/yellow]")
                lock_path.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                console.print(
                    f"[red]✗ Lock held by PID={lock_pid} (age {age:.0f}s). "
                    f"Another process is running on this series.[/red]"
                )
                console.print("[dim]Wait for it to finish, or remove the lock file manually:[/dim]")
                console.print(f"  rm {lock_path}")
                sys.exit(1)
            time.sleep(0.5)


def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID exists."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # process exists but we can't signal it


def _release_lock(lock_path: Path) -> None:
    """Release the lock acquired by _acquire_lock."""
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass


@contextmanager
def _series_lock(series_dir: Path) -> Generator[None, None, None]:
    """Context manager that acquires and releases a series lock."""
    lock_path = _acquire_lock(series_dir)
    try:
        yield
    finally:
        _release_lock(lock_path)


def _resolve_series_dir(workdir: Path) -> Path:
    """Resolve the actual series directory from a workdir path.

    If workdir itself contains series_plan.json, returns workdir.
    Otherwise looks for the most recent {timestamp}_{slug} subdirectory.
    """
    if (workdir / "series_plan.json").exists():
        return workdir
    for d in sorted(workdir.iterdir(), reverse=True):
        if d.is_dir() and "_" in d.name and not d.name.startswith("."):
            if (d / "series_plan.json").exists():
                return d
    return workdir  # not yet planned; lock will be acquired later


def _format_lock_status(series_dir: Path) -> tuple[str, str] | None:
    """Format lock status for display. Returns (style, text) or None."""
    lock_path = series_dir / _LOCK_FILE_NAME
    if not lock_path.exists():
        return None
    try:
        lock_pid = int(lock_path.read_text().strip())
        age = time.time() - lock_path.stat().st_mtime
        alive = _is_process_alive(lock_pid)
        if alive:
            return ("bold", f"🔒 lock: PID={lock_pid} (active, {age:.0f}s ago)")
        else:
            return ("dim", f"🔒 lock: PID={lock_pid} (stale, {age:.0f}s ago)")
    except (ValueError, OSError):
        return ("dim", "🔒 lock: corrupted")


def _engine(
    workdir: Path = Path("."),
    model: str = DEFAULT_MODEL,
    lang: str = "ja",
    max_review_retries: int | None = None,
    verbose: bool = False,
    raw_log: bool = False,
) -> NovelEngine:
    return NovelEngine(
        workdir=workdir, model=model, lang=lang,
        max_review_retries=max_review_retries, verbose=verbose,
        raw_log_enabled=raw_log,
    )


@app.command()
def plan(
    keywords: str = typer.Argument(..., help="Series keywords"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="LLM生データをraw_logs/に記録（動作確認用）"),
):
    """Generate a series plan from keywords."""
    series_dir = _resolve_series_dir(workdir)
    with _series_lock(series_dir):
        engine = _engine(workdir, model, lang, verbose=verbose, raw_log=raw_log)
        result = engine.plan(keywords)
        console.print(f"[green]✓[/green] Series plan generated: {result.get('title', 'N/A')}")
        console.print(f"  [dim]Output: {engine._series_dir}[/dim]")


@app.command()
def design(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="LLM生データをraw_logs/に記録（動作確認用）"),
):
    """Generate a volume design (chapter/scene structure)."""
    series_dir = _resolve_series_dir(workdir)
    with _series_lock(series_dir):
        engine = _engine(workdir, model, lang, verbose=verbose, raw_log=raw_log)
        result = engine.design(volume)
        console.print(f"[green]✓[/green] Volume {volume} design generated")


@app.command()
def write(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    max_retries: int = typer.Option(2, "--max-retries", help="Max review retries per scene"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="LLM生データをraw_logs/に記録（動作確認用）"),
):
    """Write scene drafts."""
    series_dir = _resolve_series_dir(workdir)
    with _series_lock(series_dir):
        engine = _engine(workdir, model, lang, max_review_retries=max_retries, verbose=verbose, raw_log=raw_log)
        results = engine.write(volume)
        console.print(f"[green]✓[/green] {len(results)} scenes processed")


@app.command()
def export(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="LLM生データをraw_logs/に記録（動作確認用）"),
):
    """Export manuscript for KDP."""
    series_dir = _resolve_series_dir(workdir)
    with _series_lock(series_dir):
        engine = _engine(workdir, model, lang, verbose=verbose, raw_log=raw_log)
        result = engine.export(volume)
        console.print(f"[green]✓[/green] Exported to {result['manuscript_path']}")


@app.command()
def status(
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="LLM生データをraw_logs/に記録（動作確認用）"),
):
    """Show current project status."""
    engine = _engine(workdir, model, lang, verbose=verbose, raw_log=raw_log)
    s = engine.status()
    table = Table(title="NovelForge Status")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    for k, v in s.items():
        table.add_row(k, str(v))
    # Check lock status
    series_dir = _resolve_series_dir(workdir)
    lock_info = _format_lock_status(series_dir)
    if lock_info:
        style, text = lock_info
        table.add_row(f"[{style}]{text}[/{style}]")
    console.print(table)


@app.command()
def resume(
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="LLM生データをraw_logs/に記録（動作確認用）"),
):
    """Resume from the last interrupted phase."""
    series_dir = _resolve_series_dir(workdir)
    with _series_lock(series_dir):
        engine = _engine(workdir, model, lang, verbose=verbose, raw_log=raw_log)
        result = engine.resume()
        action = result["action"]
        console.print(f"[yellow]▶[/yellow] Resume: {action} (status: {result['status']})")
        if action == "write":
            engine.write(volume)
        elif action == "design":
            engine.design(volume)
        elif action == "export":
            engine.export(volume)
        elif action == "plan":
            console.print("[red]Cannot resume plan — re-run with `plan` command.[/red]")


@app.command()
def complete(
    keywords: str = typer.Argument(..., help="Series keywords"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    max_retries: int = typer.Option(2, "--max-retries", help="Max review retries per scene"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="LLM生データをraw_logs/に記録（動作確認用）"),
):
    """Run the full pipeline: plan → design → write → export."""
    import json as _json

    series_dir = _resolve_series_dir(workdir)

    # --- State file helpers ---
    state_path = series_dir / _STATE_FILE_NAME

    def _write_state(step: str, status: str) -> None:
        try:
            state = {
                "step": step,
                "status": status,
                "model": model,
                "lang": lang,
                "pid": os.getpid(),
                "updated_at": time.time(),
            }
            state_path.write_text(_json.dumps(state, ensure_ascii=False, indent=2))
        except OSError:
            pass

    # --- Signal handler ---
    _shutdown_requested = False
    _current_step = "init"

    def _signal_handler(signum, frame):
        nonlocal _shutdown_requested
        _shutdown_requested = True
        sig_name = signal.Signals(signum).name
        console.print(f"\n[yellow]⚠ Received {sig_name} — shutting down after current step...[/yellow]")
        _write_state(_current_step, f"interrupted_by_{sig_name}")

    original_sigterm = signal.signal(signal.SIGTERM, _signal_handler)
    original_sigint = signal.signal(signal.SIGINT, _signal_handler)

    _write_state("init", "running")
    with _series_lock(series_dir):
        engine = _engine(workdir, model, lang, max_review_retries=max_retries, verbose=verbose, raw_log=raw_log)
        steps = [
            ("Plan",   lambda: engine.plan(keywords)),
            ("Design", lambda: engine.design(volume)),
            ("Write",  lambda: engine.write(volume)),
            ("Export", lambda: engine.export(volume)),
        ]
        result: dict[str, Any] | None = None
        try:
            for i, (name, fn) in enumerate(steps, 1):
                if _shutdown_requested:
                    console.print("[yellow]Shutdown requested — stopping before next step[/yellow]")
                    break
                _current_step = name
                _write_state(name, "running")
                console.print(f"[bold]Step {i}/{len(steps)}: {name}[/bold]")
                try:
                    result = fn()
                except Exception as e:
                    console.print(f"[red]✗ {name} failed: {e}[/red]")
                    _write_state(name, f"failed: {e}")
                    raise SystemExit(1) from e
                _write_state(name, "completed")
        finally:
            signal.signal(signal.SIGTERM, original_sigterm)
            signal.signal(signal.SIGINT, original_sigint)
            if result is not None:
                _write_state("done", "completed")
            # If interrupted or failed, state already written above
        assert result is not None
        console.print(f"[green]✓[/green] Complete! Manuscript: {result['manuscript_path']}")


if __name__ == "__main__":
    app()
