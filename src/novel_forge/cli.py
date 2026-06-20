from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

import typer
from rich.console import Console
from rich.table import Table

from novel_forge.engine import NovelEngine

app = typer.Typer(help="NovelForge — Local-LLM novel production pipeline")
console = Console()

_LOCK_FILE_NAME = ".lock"
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


def _engine(
    workdir: Path = Path("."),
    model: str = "qwen3.6:35b-a3b-mtp-q4_K_M",
    lang: str = "ja",
    max_review_retries: int | None = None,
    verbose: bool = False,
) -> NovelEngine:
    return NovelEngine(workdir=workdir, model=model, lang=lang, max_review_retries=max_review_retries, verbose=verbose)


@app.command()
def plan(
    keywords: str = typer.Argument(..., help="Series keywords"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option("qwen3.6:35b-a3b-mtp-q4_K_M", "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Generate a series plan from keywords."""
    series_dir = _resolve_series_dir(workdir)
    with _series_lock(series_dir):
        engine = _engine(workdir, model, lang, verbose=verbose)
        result = engine.plan(keywords)
        console.print(f"[green]✓[/green] Series plan generated: {result.get('title', 'N/A')}")
        console.print(f"  [dim]Output: {engine._series_dir}[/dim]")


@app.command()
def outline(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option("qwen3.6:35b-a3b-mtp-q4_K_M", "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Generate a volume outline."""
    series_dir = _resolve_series_dir(workdir)
    with _series_lock(series_dir):
        engine = _engine(workdir, model, lang, verbose=verbose)
        result = engine.outline(volume)
        console.print(f"[green]✓[/green] Volume {volume} outline generated")


@app.command()
def write(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option("qwen3.6:35b-a3b-mtp-q4_K_M", "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    max_retries: int = typer.Option(2, "--max-retries", help="Max review retries per scene"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Write scene drafts."""
    series_dir = _resolve_series_dir(workdir)
    with _series_lock(series_dir):
        engine = _engine(workdir, model, lang, max_review_retries=max_retries, verbose=verbose)
        results = engine.write(volume)
        console.print(f"[green]✓[/green] {len(results)} scenes processed")


@app.command()
def export(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option("qwen3.6:35b-a3b-mtp-q4_K_M", "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Export manuscript for KDP."""
    series_dir = _resolve_series_dir(workdir)
    with _series_lock(series_dir):
        engine = _engine(workdir, model, lang, verbose=verbose)
        result = engine.export(volume)
        console.print(f"[green]✓[/green] Exported to {result['manuscript_path']}")


@app.command()
def status(
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option("qwen3.6:35b-a3b-mtp-q4_K_M", "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Show current project status."""
    engine = _engine(workdir, model, lang, verbose=verbose)
    s = engine.status()
    table = Table(title="NovelForge Status")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    for k, v in s.items():
        table.add_row(k, str(v))
    # Check lock status
    series_dir = _resolve_series_dir(workdir)
    lock_path = series_dir / _LOCK_FILE_NAME
    if lock_path.exists():
        try:
            lock_pid = int(lock_path.read_text().strip())
            age = time.time() - lock_path.stat().st_mtime
            alive = _is_process_alive(lock_pid)
            if alive:
                table.add_row("🔒 lock", f"PID={lock_pid} (active, {age:.0f}s ago)")
            else:
                table.add_row("🔒 lock", f"PID={lock_pid} (stale, {age:.0f}s ago)")
        except (ValueError, OSError):
            table.add_row("🔒 lock", "corrupted")
    console.print(table)


@app.command()
def resume(
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option("qwen3.6:35b-a3b-mtp-q4_K_M", "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Resume from the last interrupted phase."""
    series_dir = _resolve_series_dir(workdir)
    with _series_lock(series_dir):
        engine = _engine(workdir, model, lang, verbose=verbose)
        result = engine.resume()
        action = result["action"]
        console.print(f"[yellow]▶[/yellow] Resume: {action} (status: {result['status']})")
        if action == "write":
            engine.write(volume)
        elif action == "outline":
            engine.outline(volume)
        elif action == "export":
            engine.export(volume)
        elif action == "plan":
            console.print("[red]Cannot resume plan — re-run with `plan` command.[/red]")


@app.command()
def complete(
    keywords: str = typer.Argument(..., help="Series keywords"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option("qwen3.6:35b-a3b-mtp-q4_K_M", "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    max_retries: int = typer.Option(2, "--max-retries", help="Max review retries per scene"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Run the full pipeline: plan → outline → write → export."""
    series_dir = _resolve_series_dir(workdir)
    with _series_lock(series_dir):
        engine = _engine(workdir, model, lang, max_review_retries=max_retries, verbose=verbose)
        console.print("[bold]Step 1/4: Plan[/bold]")
        engine.plan(keywords)
        console.print("[bold]Step 2/4: Outline[/bold]")
        engine.outline(volume)
        console.print("[bold]Step 3/4: Write[/bold]")
        engine.write(volume)
        console.print("[bold]Step 4/4: Export[/bold]")
        result = engine.export(volume)
        console.print(f"[green]✓[/green] Complete! Manuscript: {result['manuscript_path']}")


if __name__ == "__main__":
    app()
