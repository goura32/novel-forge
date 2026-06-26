"""CLI commands for NovelForge."""

from __future__ import annotations

import contextlib
from pathlib import Path

import typer

from novel_forge.engine.infra import (
    DEFAULT_MODEL,
    _find_existing_series,
    _series_lock,
    cmd_doctor,
    cmd_status,
    console,
    make_engine,
)

app = typer.Typer(help="NovelForge — Local-LLM novel production pipeline")


@app.command()
def plan(
    keywords: str = typer.Argument(..., help="Series keywords"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="Save LLM raw data"),
):
    """Generate a series plan from keywords."""
    engine = make_engine(workdir, model, lang, verbose=verbose, raw_log=raw_log, phase="plan")
    result = engine.plan(keywords)
    console.print(f"[green]✓[/green] Series plan generated: {result.get('title', 'N/A')}")
    console.print(f"  [dim]Output: {engine._series_dir}[/dim]")


@app.command()
def design(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="Save LLM raw data"),
):
    """Generate a volume design (chapter/scene structure)."""
    series_dir = _find_existing_series(workdir, series)
    with _series_lock(series_dir):
        engine = make_engine(
            series_dir, model, lang, verbose=verbose, raw_log=raw_log, phase="design"
        )
        engine.design(volume)
        console.print(f"[green]✓[/green] Volume {volume} design generated")


@app.command()
def write(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    max_retries: int = typer.Option(2, "--max-retries", help="Max review retries per scene"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="Save LLM raw data"),
):
    """Write scene drafts."""
    series_dir = _find_existing_series(workdir, series)
    with _series_lock(series_dir):
        engine = make_engine(
            series_dir,
            model,
            lang,
            max_review_retries=max_retries,
            verbose=verbose,
            raw_log=raw_log,
            phase="write",
        )
        results = engine.write(volume)
        console.print(f"[green]✓[/green] {len(results)} scenes processed")


@app.command()
def export(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="Save LLM raw data"),
):
    """Export manuscript for KDP."""
    series_dir = _find_existing_series(workdir, series)
    with _series_lock(series_dir):
        engine = make_engine(
            series_dir, model, lang, verbose=verbose, raw_log=raw_log, phase="export"
        )
        result = engine.export(volume)
        console.print(f"[green]✓[/green] Exported to {result['manuscript_path']}")


@app.command()
def status(
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
):
    """Show current project status."""
    series_dir = _find_existing_series(workdir, series) if series else workdir
    engine = make_engine(series_dir, phase="status")
    cmd_status(engine)


@app.command()
def resume(
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    raw_log: bool = typer.Option(False, "--raw-log", help="Save LLM raw data"),
):
    """Resume from the last interrupted phase."""
    series_dir = _find_existing_series(workdir, series)
    with _series_lock(series_dir):
        engine = make_engine(
            series_dir, model, lang, verbose=verbose, raw_log=raw_log, phase="resume"
        )
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
    raw_log: bool = typer.Option(False, "--raw-log", help="Save LLM raw data"),
):
    """Run the full pipeline: plan → design → write → export."""
    engine = make_engine(
        workdir,
        model,
        lang,
        max_review_retries=max_retries,
        verbose=verbose,
        raw_log=raw_log,
        phase="complete",
    )
    steps = [
        ("Plan", lambda: engine.plan(keywords)),
        ("Design", lambda: engine.design(volume)),
        ("Write", lambda: engine.write(volume)),
        ("Export", lambda: engine.export(volume)),
    ]
    result = None
    try:
        for i, (name, fn) in enumerate(steps, 1):
            console.print(f"[bold]Step {i}/{len(steps)}: {name}[/bold]")
            try:
                result = fn()
            except Exception as e:
                console.print(f"[red]✗ {name} failed: {e}[/red]")
                raise SystemExit(1) from e
    finally:
        assert result is not None
        console.print(
            f"[green]✓[/green] Complete! Manuscript: {result.get('manuscript_path', result.get('manuscript', 'N/A'))}"
        )


@app.command()
def doctor(
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Model to test"),
    ollama_host: str = typer.Option("ws1.local:11434", "--ollama-host", help="Ollama host"),
):
    """Diagnose Ollama connectivity and model readiness."""
    cmd_doctor(model, ollama_host)


@app.command()
def list(
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
):
    """List all series in the working directory."""
    from rich.table import Table

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
            import json as _json

            plan = _json.loads(plan_path.read_text(encoding="utf-8"))
            slug = plan.get("slug", d.name)
            title = plan.get("title", "?")
            volumes = len(plan.get("planned_volumes", []))
            state_path = d / ".novel_forge_state"
            st = "unknown"
            if state_path.exists():
                with contextlib.suppress(Exception):
                    st = _json.loads(state_path.read_text(encoding="utf-8")).get("status", "?")
            table.add_row(slug, title, str(volumes), st)
        except Exception:
            pass

    console.print(table)
