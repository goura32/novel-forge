"""CLI commands for NovelForge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import typer

from novel_forge.config import RuntimeConfig
from novel_forge.engine.infra import (
    _find_existing_series,
    _resolve_doctor_defaults,
    cmd_doctor,
    cmd_status,
    console,
    make_engine,
)
from novel_forge.logging_config import get_logger
from novel_forge.runtime import (
    RunManager,
    RunRepository,
    SeriesSlugExistsError,
)

app = typer.Typer(help="NovelForge — Local-LLM novel production pipeline")
_log = get_logger("novel_forge.cli")


@app.command()
def plan(
    keywords: str = typer.Argument(..., help="Series keywords"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model override"),
    max_generation_count: int | None = typer.Option(None, "--max-generation-count", help="Max generation (API+validation) retries per phase"),
    max_review_count: int | None = typer.Option(None, "--max-review-count", help="Max review cycles per phase"),
    verbose: bool | None = typer.Option(None, "--verbose", "-v", help="Verbose output"),
):
    """Generate a series plan from keywords."""
    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(workdir)
    repo = RunRepository(resolved_workdir)
    manager = RunManager(repo)
    run = repo.create_run(command="plan", model=model or config.llm.model, verbose=bool(verbose), input_snapshot_id=None)
    workspace_lock = manager.acquire(scope="workspace", run=run, phase="plan")
    try:
        engine = make_engine(
            resolved_workdir, model, "ja", verbose=verbose, phase="plan",
            max_generation_count=max_generation_count,
            max_review_count=max_review_count,
            run=run,
            repository=repo,
            manager=manager,
            workspace_lock=workspace_lock,
        )
        result = engine.plan(keywords)
        console.print(f"[green]✓[/green] Series plan generated: {result.get('title', 'N/A')}")
        console.print(f"  [dim]Run: {run.manifest.run_id}[/dim]")
    finally:
        workspace_lock.release()


@app.command()
def design(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number (0=all)"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model override"),
    max_generation_count: int | None = typer.Option(None, "--max-generation-count", help="Max generation (API+validation) retries per phase"),
    max_review_count: int | None = typer.Option(None, "--max-review-count", help="Max review cycles per phase"),
    verbose: bool | None = typer.Option(None, "--verbose", "-v", help="Verbose output"),
):
    """Generate a volume design (chapter/scene structure)."""
    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(workdir)
    repo = RunRepository(resolved_workdir)
    manager = RunManager(repo)
    series_dir = _find_existing_series(resolved_workdir, series)
    run = repo.create_run(command="design", model=model or config.llm.model, verbose=bool(verbose), input_snapshot_id=None)
    with manager.side_effect_scope(scope=f"series-{series_dir.name}", run=run, phase="design"):
        engine = make_engine(
            series_dir, model, "ja", verbose=verbose, phase="design",
            max_generation_count=max_generation_count,
            max_review_count=max_review_count,
            run=run, repository=repo, manager=manager,
        )
        if volume == 0:
            # Generate all volumes
            plan_path = series_dir / "series_plan.json"
            if plan_path.exists():
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                total_vol = len(plan.get("planned_volumes", []))
            else:
                total_vol = 2
            for v in range(1, total_vol + 1):
                engine.design(v)
                console.print(f"[green]✓[/green] Volume {v}/{total_vol} design generated")
        else:
            engine.design(volume)
            console.print(f"[green]✓[/green] Volume {volume} design generated")


@app.command()
def write(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model override"),
    max_generation_count: int | None = typer.Option(None, "--max-generation-count", help="Max generation (API+validation) retries per scene"),
    max_review_count: int | None = typer.Option(None, "--max-review-count", help="Max review cycles per scene"),
    verbose: bool | None = typer.Option(None, "--verbose", "-v", help="Verbose output"),
):
    """Write scene drafts."""
    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(workdir)
    repo = RunRepository(resolved_workdir)
    manager = RunManager(repo)
    series_dir = _find_existing_series(resolved_workdir, series)
    run = repo.create_run(command="write", model=model or config.llm.model, verbose=bool(verbose), input_snapshot_id=None)
    with manager.side_effect_scope(scope=f"series-{series_dir.name}", run=run, phase="write"):
        engine = make_engine(
            series_dir,
            model,
            "ja",
            max_generation_count=max_generation_count,
            max_review_count=max_review_count,
            verbose=verbose,
            phase="write",
            run=run, repository=repo, manager=manager,
        )
        results = engine.write(volume)
        console.print(f"[green]✓[/green] {len(results)} scenes processed")


@app.command()
def export(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model override"),
    verbose: bool | None = typer.Option(None, "--verbose", "-v", help="Verbose output"),
):
    """Export manuscript for KDP."""
    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(workdir)
    repo = RunRepository(resolved_workdir)
    manager = RunManager(repo)
    series_dir = _find_existing_series(resolved_workdir, series)
    run = repo.create_run(command="export", model=model or config.llm.model, verbose=bool(verbose), input_snapshot_id=None)
    with manager.side_effect_scope(scope=f"series-{series_dir.name}", run=run, phase="export"):
        engine = make_engine(
            series_dir, model, "ja", verbose=verbose, phase="export",
            run=run, repository=repo, manager=manager,
        )
        result = engine.export(volume)
        console.print(f"[green]✓[/green] Exported to {result['manuscript_path']}")


@app.command()
def status(
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
):
    """Show current project status."""
    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(workdir)
    repo = RunRepository(resolved_workdir)
    series_dir = _find_existing_series(resolved_workdir, series) if series else resolved_workdir
    engine = make_engine(series_dir, phase="status", run=repo.create_run(command="status", model=config.llm.model, verbose=False, input_snapshot_id=None), repository=repo, manager=RunManager(repo))
    cmd_status(engine)


@app.command()
def resume(
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model override"),
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    max_generation_count: int | None = typer.Option(None, "--max-generation-count", help="Max generation (API+validation) retries per phase"),
    max_review_count: int | None = typer.Option(None, "--max-review-count", help="Max review cycles per phase"),
    verbose: bool | None = typer.Option(None, "--verbose", "-v", help="Verbose output"),
):
    """Resume from the last interrupted phase."""
    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(workdir)
    repo = RunRepository(resolved_workdir)
    manager = RunManager(repo)
    series_dir = _find_existing_series(resolved_workdir, series)
    run = repo.create_run(command="resume", model=model or config.llm.model, verbose=bool(verbose), input_snapshot_id=None)
    with manager.side_effect_scope(scope=f"series-{series_dir.name}", run=run, phase="resume"):
        engine = make_engine(
            series_dir, model, "ja", verbose=verbose, phase="resume",
            max_generation_count=max_generation_count,
            max_review_count=max_review_count,
            run=run, repository=repo, manager=manager,
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
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model override"),
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    max_generation_count: int | None = typer.Option(None, "--max-generation-count", help="Max generation (API+validation) retries per scene"),
    max_review_count: int | None = typer.Option(None, "--max-review-count", help="Max review cycles per scene"),
    verbose: bool | None = typer.Option(None, "--verbose", "-v", help="Verbose output"),
):
    """Run the full pipeline: plan → design → write → export."""
    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(workdir)
    repo = RunRepository(resolved_workdir)
    manager = RunManager(repo)
    run = repo.create_run(command="complete", model=model or config.llm.model, verbose=bool(verbose), input_snapshot_id=None)
    workspace_lock = manager.acquire(scope="workspace", run=run, phase="complete")
    try:
        engine = make_engine(
            resolved_workdir,
            model,
            "ja",
            max_generation_count=max_generation_count,
            max_review_count=max_review_count,
            verbose=verbose,
            phase="complete",
            run=run, repository=repo, manager=manager, workspace_lock=workspace_lock,
        )
        slug: str | None = None
        steps = [
            ("Plan", lambda: engine.plan(keywords)),
            ("Design", lambda: engine.design(volume)),
            ("Write", lambda: engine.write(volume)),
            ("Export", lambda: engine.export(volume)),
        ]
        result: dict[str, Any] | None = None
        for i, (name, fn) in enumerate(steps, 1):
            console.print(f"[bold]Step {i}/{len(steps)}: {name}[/bold]")
            try:
                result = cast(dict[str, Any], fn())
                if name == "Plan" and isinstance(result, dict):
                    slug = result.get("slug")
            except SeriesSlugExistsError:
                workspace_lock.release()
                raise
            except Exception as e:
                workspace_lock.release()
                console.print(f"[red]✗ {name} failed: {e}[/red]")
                raise SystemExit(1) from e
        if slug and (repo.series_runtime_root(slug) / "ledger").exists():
            manager.promote_plan_to_series(workspace_lock=workspace_lock, run=run, slug=slug)
    finally:
        workspace_lock.release()
    console.print(
        f"[green]✓[/green] Complete! Manuscript: "
        f"{(result or {}).get('manuscript_path', (result or {}).get('manuscript', 'N/A'))}"
    )
@app.command()
def doctor(
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str | None = typer.Option(None, "--model", "-m", help="Model override to test"),
    ollama_host: str | None = typer.Option(None, "--ollama-host", help="Ollama host override"),
):
    """Diagnose Ollama connectivity and model readiness."""
    resolved_model, resolved_host = _resolve_doctor_defaults(workdir, model, ollama_host)
    cmd_doctor(resolved_model, resolved_host)


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

    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(workdir)
    repo = RunRepository(resolved_workdir)
    for d in sorted(resolved_workdir.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        ledger = repo.series_runtime_root(d.name) / "ledger"
        if not ledger.exists():
            continue
        plan_path = d / "series_plan.json"
        if not plan_path.exists():
            table.add_row(d.name, "?", "?", "no-plan")
            continue
        try:
            import json as _json

            plan = _json.loads(plan_path.read_text(encoding="utf-8"))
            slug = plan.get("slug", d.name)
            title = plan.get("title", "?")
            volumes = len(plan.get("planned_volumes", []))
            st = "exists"
            table.add_row(slug, title, str(volumes), st)
        except Exception as exc:
            _log.warning("Failed to read series plan while listing: %s", plan_path, exc_info=exc)

    console.print(table)


if __name__ == "__main__":
    app()