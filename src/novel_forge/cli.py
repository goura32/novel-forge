from __future__ import annotations

import os
import signal
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

from novel_forge.engine import NovelEngine

app = typer.Typer(help="NovelForge — Local-LLM novel production pipeline")
console = Console()

DEFAULT_MODEL = "qwen3.6:35b-a3b-mtp-q4_K_M"
_LOCK_FILE_NAME = ".lock"
_STATE_FILE_NAME = ".novel_forge_state"
_LOCK_TIMEOUT_SECONDS = 300


def _acquire_lock(series_dir: Path, timeout: float | None = None) -> Path:
    """Acquire an exclusive lock for a series directory.

    If a stale lock is detected (process no longer alive), it is overwritten
    immediately. Otherwise, waits up to ``timeout`` seconds.
    """
    if timeout is None:
        timeout = _LOCK_TIMEOUT_SECONDS
    lock_path = series_dir / _LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Check for stale lock first — overwrite immediately if holder is dead
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
                    console.print("[dim]Wait for it to finish, or remove the lock file manually:[/dim]")
                    console.print(f"  rm {lock_path}")
                    sys.exit(1)
                now = time.monotonic()
                if now - last_msg >= 5.0:
                    waited = now - (deadline - timeout)
                    console.print(f"[dim]⏳ Waiting for lock (PID={lock_pid}, waited {waited:.0f}s)...[/dim]")
                    last_msg = now
                time.sleep(0.5)
            else:
                # Lock became stale while we were waiting — remove and retry
                lock_path.unlink(missing_ok=True)


def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID exists."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


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


def _resolve_series_dir(workdir: Path, slug: str | None = None) -> Path:
    """Resolve the actual series directory.

    If slug is given, look for {slug} directory in workdir.
    Otherwise, look for the most recent series directory or return workdir
    (for plan command which creates a new one).
    """
    if slug:
        series_dir = workdir / slug
        if not series_dir.exists():
            raise FileNotFoundError(
                f"Series '{slug}' not found in {workdir}. "
                f"Run 'plan' first, or check the slug name."
            )
        return series_dir
    # No slug: check if workdir itself is a series dir
    if (workdir / "series_plan.json").exists():
        return workdir
    # Look for {slug} directory
    for d in sorted(workdir.iterdir(), reverse=True):
        if d.is_dir() and not d.name.startswith("."):
            if (d / "series_plan.json").exists():
                return d
    return workdir  # not yet planned


def _engine(
    workdir: Path = Path("."),
    model: str = DEFAULT_MODEL,
    lang: str = "ja",
    max_review_retries: int | None = None,
    verbose: bool | None = None,
    raw_log: bool | None = None,
    phase: str = "",
) -> NovelEngine:
    engine = NovelEngine(
        workdir=workdir, model=model, lang=lang,
        max_review_retries=max_review_retries, verbose=verbose,
        raw_log_enabled=raw_log,
        phase=phase,
    )

    _shutdown_requested = False
    _current_step = "init"

    def _signal_handler(signum, frame):
        nonlocal _shutdown_requested
        _shutdown_requested = True
        sig_name = signal.Signals(signum).name
        engine._log.warning(f"Received {sig_name} — shutting down after current step")
        console.print(f"\n[yellow]⚠ Received {sig_name} — shutting down after current step...[/yellow]")
        try:
            state_path = engine._series_dir / ".novel_forge_state"
            import json as _json
            state = {
                "step": _current_step,
                "status": f"interrupted_by_{sig_name}",
                "model": model, "lang": lang, "pid": os.getpid(),
                "updated_at": time.time(),
            }
            state_path.write_text(_json.dumps(state, ensure_ascii=False, indent=2))
        except Exception:
            pass

    original_sigterm = signal.signal(signal.SIGTERM, _signal_handler)
    original_sigint = signal.signal(signal.SIGINT, _signal_handler)
    engine._signal_cleanup = (original_sigterm, original_sigint)
    return engine


@app.command()
def plan(
    keywords: str = typer.Argument(..., help="Series keywords"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory (contains config.yaml)"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="Save LLM raw data to _raw_logs/"),
):
    """Generate a series plan from keywords."""
    engine = _engine(workdir, model, lang, verbose=verbose, raw_log=raw_log, phase="plan")
    result = engine.plan(keywords)
    console.print(f"[green]✓[/green] Series plan generated: {result.get('title', 'N/A')}")
    console.print(f"  [dim]Output: {engine._series_dir}[/dim]")


@app.command()
def design(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory (contains config.yaml)"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug (e.g. closed-stacks-return-box)"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="Save LLM raw data to _raw_logs/"),
):
    """Generate a volume design (chapter/scene structure)."""
    series_dir = _resolve_series_dir(workdir, series)
    with _series_lock(series_dir):
        engine = _engine(series_dir, model, lang, verbose=verbose, raw_log=raw_log, phase="design")
        result = engine.design(volume)
        console.print(f"[green]✓[/green] Volume {volume} design generated")


@app.command()
def write(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory (contains config.yaml)"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    max_retries: int = typer.Option(2, "--max-retries", help="Max review retries per scene"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="Save LLM raw data to _raw_logs/"),
):
    """Write scene drafts."""
    series_dir = _resolve_series_dir(workdir, series)
    with _series_lock(series_dir):
        engine = _engine(series_dir, model, lang, max_review_retries=max_retries, verbose=verbose, raw_log=raw_log, phase="write")
        results = engine.write(volume)
        console.print(f"[green]✓[/green] {len(results)} scenes processed")


@app.command()
def export(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory (contains config.yaml)"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="Save LLM raw data to _raw_logs/"),
):
    """Export manuscript for KDP."""
    series_dir = _resolve_series_dir(workdir, series)
    with _series_lock(series_dir):
        engine = _engine(series_dir, model, lang, verbose=verbose, raw_log=raw_log, phase="export")
        result = engine.export(volume)
        console.print(f"[green]✓[/green] Exported to {result['manuscript_path']}")


@app.command()
def status(
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory (contains config.yaml)"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Show current project status."""
    series_dir = _resolve_series_dir(workdir, series) if series else workdir
    engine = _engine(series_dir, model, lang, verbose=verbose, phase="status")
    s = engine.status()
    table = Table(title="NovelForge Status")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    for k, v in s.items():
        table.add_row(k, str(v))
    lock_path = series_dir / _LOCK_FILE_NAME
    if lock_path.exists():
        try:
            lock_pid = int(lock_path.read_text().strip())
            age = time.time() - lock_path.stat().st_mtime
            alive = _is_process_alive(lock_pid)
            if alive:
                table.add_row(f"[bold]🔒 lock: PID={lock_pid} (active, {age:.0f}s ago)[/bold]", "")
            else:
                table.add_row(f"[dim]🔒 lock: PID={lock_pid} (stale, {age:.0f}s ago)[/dim]", "")
        except (ValueError, OSError):
            table.add_row("[dim]🔒 lock: corrupted[/dim]", "")
    console.print(table)


@app.command()
def resume(
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory (contains config.yaml)"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="Save LLM raw data to _raw_logs/"),
):
    """Resume from the last interrupted phase."""
    series_dir = _resolve_series_dir(workdir, series)
    with _series_lock(series_dir):
        engine = _engine(series_dir, model, lang, verbose=verbose, raw_log=raw_log, phase="resume")
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
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory (contains config.yaml)"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    max_retries: int = typer.Option(2, "--max-retries", help="Max review retries per scene"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="Save LLM raw data to _raw_logs/"),
):
    """Run the full pipeline: plan → design → write → export."""
    import json as _json

    series_dir = _resolve_series_dir(workdir)
    state_path = series_dir / _STATE_FILE_NAME

    def _write_state(step: str, status: str) -> None:
        try:
            state = {"step": step, "status": status, "model": model, "lang": lang, "pid": os.getpid(), "updated_at": time.time()}
            state_path.write_text(_json.dumps(state, ensure_ascii=False, indent=2))
        except OSError:
            pass

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
    engine = _engine(series_dir, model, lang, max_review_retries=max_retries, verbose=verbose, raw_log=raw_log, phase="complete")
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
                if name == "Plan":
                    result = fn()
                else:
                    series_dir = _resolve_series_dir(workdir)
                    with _series_lock(series_dir):
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
        assert result is not None
        console.print(f"[green]✓[/green] Complete! Manuscript: {result['manuscript_path']}")


@app.command()
def doctor(
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Model to test"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    ollama_host: str = typer.Option("ws1.local:11434", "--ollama-host", help="Ollama host"),
):
    """Diagnose Ollama connectivity and model readiness."""
    import json as _json

    console.print("[bold]NovelForge Doctor[/bold]")
    print()

    # 1. Check Ollama is running
    console.print("1. Ollama connectivity")
    try:
        resp = httpx.get(f"http://{ollama_host}/", timeout=5)
        if resp.status_code == 200:
            console.print("   [green]✓ Ollama is running[/green]")
        else:
            console.print(f"   [red]✗ Ollama returned status {resp.status_code}[/red]")
            return
    except Exception as e:
        console.print(f"   [red]✗ Cannot reach Ollama: {e}[/red]")
        return

    # 2. Check required model
    print()
    console.print(f"2. Model: {model}")
    try:
        resp = httpx.post(f"http://{ollama_host}/api/show", json={"name": model}, timeout=15)
        if resp.status_code == 200:
            info = resp.json()
            details = info.get("details", {})
            ctx = details.get("context_length", "?")
            fmt = details.get("format", "?")
            fam = details.get("family", "?")
            console.print(f"   [green]✓ Model loaded[/green]")
            console.print(f"   context_length: {ctx}, format: {fmt}, family: {fam}")
        else:
            console.print(f"   [yellow]⚠ Model info status {resp.status_code}[/yellow]")
            console.print(f"   Run: ollama pull {model}")
    except Exception as e:
        console.print(f"   [red]✗ Model check failed: {e}[/red]")

    # 3. Test simple inference (thinking=False)
    print()
    console.print("3. Inference test (thinking=False)")
    try:
        payload = {
            "model": model, "messages": [{"role": "user", "content": "Reply with only: OK"}],
            "stream": True, "format": "json", "options": {"think": False, "num_predict": 500},
        }
        content_parts = []
        with httpx.stream("POST", f"http://{ollama_host}/api/chat", json=payload, timeout=120) as stream_resp:
            for line in stream_resp.iter_lines():
                if not line.strip():
                    continue
                chunk = _json.loads(line)
                if chunk.get("done"):
                    console.print(f"   done_reason: {chunk.get('done_reason', '')}")
                    break
                msg = chunk.get("message", {})
                if msg.get("content"):
                    content_parts.append(msg["content"])
        content = "".join(content_parts)
        if content:
            console.print(f"   [green]✓ content: [{content[:200]}][/green]")
        else:
            console.print(f"   [yellow]⚠ Empty content[/yellow]")
    except Exception as e:
        console.print(f"   [red]✗ Inference failed: {e}[/red]")

    # 4. Test inference with thinking=True
    print()
    console.print("4. Inference test (thinking=True)")
    try:
        payload = {
            "model": model, "messages": [{"role": "user", "content": "Reply with only: OK"}],
            "stream": True, "format": "json", "options": {"think": True, "num_predict": 500},
        }
        content_parts = []
        with httpx.stream("POST", f"http://{ollama_host}/api/chat", json=payload, timeout=300) as stream_resp:
            for line in stream_resp.iter_lines():
                if not line.strip():
                    continue
                chunk = _json.loads(line)
                if chunk.get("done"):
                    console.print(f"   done_reason: {chunk.get('done_reason', '')}")
                    break
                msg = chunk.get("message", {})
                if msg.get("content"):
                    content_parts.append(msg["content"])
        content = "".join(content_parts)
        if content:
            console.print(f"   [green]✓ content: [{content[:200]}][/green]")
        else:
            console.print(f"   [yellow]⚠ Empty content[/yellow]")
    except Exception as e:
        console.print(f"   [red]✗ Inference failed: {e}[/red]")

    # 5. Test JSON format
    print()
    console.print("5. JSON format test")
    try:
        payload = {
            "model": model, "messages": [{"role": "user", "content": '{"key": "value"}'}],
            "stream": False, "format": "json", "options": {"think": False, "num_predict": 50},
        }
        resp = httpx.post(f"http://{ollama_host}/api/chat", json=payload, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            parsed = _json.loads(content)
            console.print(f"   [green]✓ JSON parseable: {parsed}[/green]")
        else:
            console.print(f"   [yellow]⚠ Status {resp.status_code}[/yellow]")
    except Exception as e:
        console.print(f"   [red]✗ JSON test failed: {e}[/red]")

    print()
    console.print("[bold]Done.[/bold]")


@app.command()
def list(
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
):
    """List all series in the working directory."""
    import json as _json

    table = Table(title="NovelForge Series")
    table.add_column("Slug", style="bold")
    table.add_column("Title")
    table.add_column("Volumes")
    table.add_column("Status")

    for d in sorted(workdir.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        plan_path = d / "series_plan.json"
        if not plan_path.exists():
            continue
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            slug = plan.get("slug", d.name)
            title = plan.get("title", "?")
            volumes = len(plan.get("planned_volumes", []))
            state_path = d / ".novel_forge_state"
            st = "unknown"
            if state_path.exists():
                try:
                    st = json.loads(state_path.read_text(encoding="utf-8")).get("status", "?")
                except Exception:
                    pass
            table.add_row(slug, title, str(volumes), st)
        except Exception:
            pass

    console.print(table)
