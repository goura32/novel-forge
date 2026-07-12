"""CLI commands for NovelForge."""

from __future__ import annotations

import builtins
import json
import re
from pathlib import Path
from typing import Any

import httpx as _httpx
import typer
from rich.console import Console
from rich.table import Table

from novel_forge.canon.store import BibleFactory
from novel_forge.config import RuntimeConfig
from novel_forge.logging_config import get_logger
from novel_forge.prompts import PromptManager
from novel_forge.runtime import (
    RunHandle,
    RunManager,
    RunRepository,
    RuntimeContractError,
    sanitize_for_storage,
)
from novel_forge.workflow_runtime import RuntimeWorkflow
from novel_forge.workflow_task_runner import make_task_runner

console = Console()
_log = get_logger("novel_forge.cli")


# ---------------------------------------------------------------------------
# Doctor helpers (migrated from deleted engine.infra)
# ---------------------------------------------------------------------------


def _resolve_doctor_defaults(
    workdir: Path | None,
    model: str | None,
    ollama_host: str | None,
) -> tuple[str, str]:
    """Resolve doctor options from canonical config; workdir is intentionally ignored."""
    del workdir
    llm_cfg = RuntimeConfig.load().llm
    resolved_model = model if model is not None else llm_cfg.model
    resolved_host = (
        ollama_host
        if ollama_host is not None
        else llm_cfg.ollama_host
    )
    return resolved_model, resolved_host


def _workdir_config_path(workdir: Path) -> Path | None:
    candidate = workdir / "config.yaml"
    return candidate if candidate.exists() else None


def cmd_doctor(
    model: str = RuntimeConfig().llm.model,
    ollama_host: str = "ws1.local:11434",
) -> None:
    """Diagnose Ollama connectivity and model readiness."""
    console.print("[bold]NovelForge Doctor[/bold]\n")

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

    console.print(f"\n2. Model: {model}")
    try:
        resp = _httpx.post(f"http://{ollama_host}/api/show", json={"name": model}, timeout=15)
        if resp.status_code == 200:
            details = resp.json().get("details", {})
            console.print("   [green]✓ Model loaded[/green]")
            console.print(f"   context_length: {details.get('context_length', '?')}")
            console.print(f"   format: {details.get('format', '?')}")
        else:
            console.print(f"   [yellow]⚠ Status {resp.status_code}[/yellow]")
            console.print(f"   Run: ollama pull {model}")
    except Exception as e:
        console.print(f"   [red]✗ Check failed: {e}[/red]")

    console.print("\n[bold]Done.[/bold]")


def _find_existing_series(workdir: Path, slug: str | None = None) -> Path:
    """Find a series from its immutable runtime ledger, never legacy files."""
    root = workdir.resolve()
    repo = RunRepository(root, read_only=True)
    if slug:
        if not re.fullmatch(r"[a-z0-9_]+", slug):
            raise ValueError(f"Unsafe series slug: {slug}")
        series_dir = repo.series_root(slug)
        if not repo.ledger_root(slug).is_dir():
            raise FileNotFoundError(f"Series '{slug}' not found in {workdir}")
        return series_dir

    candidates = [
        path
        for path in sorted(root.iterdir(), reverse=True)
        if path.is_dir() and not path.name.startswith(".") and repo.ledger_root(path.name).is_dir()
    ]
    if not candidates:
        raise FileNotFoundError(f"No runtime-managed series found in {workdir}")
    if len(candidates) > 1:
        raise RuntimeContractError("Multiple series found; pass --series explicitly")
    return candidates[0]


def _existing_series_slugs(workdir: Path) -> builtins.list[str]:
    """Return only runtime-managed series slugs for plan collision checks."""
    root = workdir.resolve()
    repo = RunRepository(root, read_only=True)
    return [
        path.name
        for path in sorted(root.iterdir())
        if path.is_dir() and not path.name.startswith(".") and repo.ledger_root(path.name).is_dir()
    ]


def _selected_payload(repo: RunRepository, slug: str, snapshot_id: str, slot: str) -> dict[str, Any]:
    """Read a verified selected artifact from an immutable snapshot."""
    snapshot = repo.load_snapshot(slug, snapshot_id)
    try:
        artifact_id = snapshot.slots[slot]
    except KeyError as exc:
        raise RuntimeContractError(f"selected snapshot is missing required slot: {slot}") from exc
    payload = repo.read_payload(repo.verify_artifact(artifact_id))
    if not isinstance(payload, dict):
        raise RuntimeContractError(f"selected artifact payload must be an object: {slot}")
    return payload


def _make_workflow(
    repo: RunRepository,
    run: RunHandle,
    slug: str | None,
    config: RuntimeConfig,
    model: str | None,
    max_review_count: int | None,
    max_summary_review_count: int | None,
    verbose: bool | None,
) -> RuntimeWorkflow:
    """Build a RuntimeWorkflow wired to the real LLM task runner."""
    from novel_forge.llm_client import LLMClient

    client = LLMClient(
        api_url=f"http://{config.llm.ollama_host}/api/chat",
        model=model or config.llm.model,
        timeout_seconds=config.llm.timeout_seconds,
        ollama_options=config.llm.ollama_options,
        series_slug=slug or "",
    )
    task_runner = make_task_runner(client, PromptManager())
    return RuntimeWorkflow(
        repository=repo,
        run=run,
        slug=slug,
        task_runner=task_runner,
        max_review_count=max_review_count or config.quality.max_review_count,
        max_summary_review_count=max_summary_review_count or config.quality.max_summary_review_count,
        max_retry_count=config.quality.max_retry_count,
    )


def _resolve_verbose(config: RuntimeConfig, cli_verbose: bool | None) -> bool:
    """Resolve verbose with explicit CLI input taking priority over canonical config."""
    return cli_verbose if cli_verbose is not None else config.verbose


def _setup_command_logging(config: RuntimeConfig) -> None:
    """Initialize logging while accepting minimal config objects used by CLI callers."""
    from novel_forge.logging_config import setup_logging

    logging_config = getattr(config, "logging", None)
    setup_logging(
        log_file=None,
        verbose=config.verbose,
        log_level=getattr(logging_config, "level", "INFO"),
    )


app = typer.Typer(help="NovelForge — Local-LLM novel production pipeline")
_log = get_logger("novel_forge.cli")


@app.callback()
def _main_callback() -> None:
    """Initialize logging from config before any command runs."""
    from novel_forge.config import RuntimeConfig

    _setup_command_logging(RuntimeConfig.load())


@app.command()
def plan(
    keywords: str = typer.Argument(..., help="Series keywords"),
    workdir: Path | None = typer.Option(None, "--workdir", "-w", help="Working directory"),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model override"),
    max_review_count: int | None = typer.Option(None, "--max-review-count", help="Max review cycles per phase"),
    max_summary_review_count: int | None = typer.Option(None, "--max-summary-review-count", help="Max summary review cycles"),
    verbose: bool | None = typer.Option(None, "--verbose", "-v", help="Verbose output"),
    wait_lock: bool = typer.Option(False, "--wait-lock", help="Wait for the run lock instead of failing fast on contention"),
):
    """Generate a series plan from keywords and bootstrap the immutable series root."""
    _cfg = RuntimeConfig.load()
    _setup_command_logging(_cfg)
    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(workdir)
    repo = RunRepository(resolved_workdir)
    manager = RunManager(repo)
    run = repo.create_run(command="plan", model=model or config.llm.model, verbose=_resolve_verbose(config, verbose), input_snapshot_id=None)
    workspace_lock = manager.acquire(scope="workspace", run=run, phase="plan", wait=wait_lock)
    series_lock = None
    try:
        workflow = _make_workflow(
            repo, run, None, config, model, max_review_count, max_summary_review_count, verbose
        )
        existing = _existing_series_slugs(resolved_workdir)
        plan_attempt, plan = workflow._run_task(
            "plan.series.generate",
            {"keywords": keywords, "existing_slugs": existing},
            reason="generate series plan",
        )
        plan_attempt, plan = workflow._review_and_revise(
            "plan.series", plan, plan_attempt,
            review_values=lambda candidate: {"plan": candidate},
            revise_values=lambda candidate, review: {"current_plan": candidate, "review": review},
            contract_issues=lambda candidate: (
                [] if isinstance(candidate.get("slug"), str) and re.fullmatch(r"[a-z0-9_]{1,40}", candidate["slug"])
                else [{"severity": "error", "category": "contract", "message": "slug must match [a-z0-9_]{1,40}; it is not normalized by runtime"}]
            ),
        )
        slug = plan["slug"]
        series_lock = manager.promote_plan_to_series(
            workspace_lock=workspace_lock, run=run, slug=slug
        )
        canon_seed = BibleFactory.create_seed(plan).model_dump(mode="json")
        workflow.bootstrap_plan(slug=slug, plan=plan, canon_seed=canon_seed, plan_attempt=plan_attempt)
        console.print(f"[green]✓[/green] Series plan generated: {plan.get('title', 'N/A')} (slug: {slug})")
        console.print(f"  [dim]Run: {run.manifest.run_id}[/dim]")
    finally:
        if series_lock is not None:
            series_lock.release()
        workspace_lock.release()


@app.command()
def design(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number (0=all)"),
    workdir: Path | None = typer.Option(None, "--workdir", "-w", help="Working directory"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model override"),
    max_review_count: int | None = typer.Option(None, "--max-review-count", help="Max review cycles per phase"),
    max_summary_review_count: int | None = typer.Option(None, "--max-summary-review-count", help="Max summary review cycles"),
    verbose: bool | None = typer.Option(None, "--verbose", "-v", help="Verbose output"),
    wait_lock: bool = typer.Option(False, "--wait-lock", help="Wait for the run lock instead of failing fast on contention"),
):
    """Generate a volume design (chapter/scene structure) and publish it."""
    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(workdir)
    repo = RunRepository(resolved_workdir)
    manager = RunManager(repo)
    series_dir = _find_existing_series(resolved_workdir, series)
    snapshot_id = repo.current_snapshot_id(series_dir.name)
    run = repo.create_run(
        command="design",
        model=model or config.llm.model,
        verbose=_resolve_verbose(config, verbose),
        input_snapshot_id=snapshot_id,
    )
    with manager.side_effect_scope(scope=f"series-{series_dir.name}", run=run, phase="design", wait=wait_lock):
        workflow = _make_workflow(
            repo, run, series_dir.name, config, model, max_review_count, max_summary_review_count, verbose
        )
        plan = _selected_payload(repo, series_dir.name, snapshot_id, "plan.series")
        total_vol = len(plan.get("planned_volumes", [])) or 2
        volumes = range(1, total_vol + 1) if volume == 0 else range(volume, volume + 1)
        for v in volumes:
            snapshot = workflow.generate_volume_design(volume=v, plan=plan)
            console.print(f"[green]✓[/green] Volume {v} design generated (snapshot: {snapshot.selection_snapshot_id})")


@app.command()
def write(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path | None = typer.Option(None, "--workdir", "-w", help="Working directory"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model override"),
    max_review_count: int | None = typer.Option(None, "--max-review-count", help="Max review cycles per scene"),
    max_summary_review_count: int | None = typer.Option(None, "--max-summary-review-count", help="Max summary review cycles"),
    verbose: bool | None = typer.Option(None, "--verbose", "-v", help="Verbose output"),
    wait_lock: bool = typer.Option(False, "--wait-lock", help="Wait for the run lock instead of failing fast on contention"),
):
    """Write scene drafts for a volume."""
    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(workdir)
    repo = RunRepository(resolved_workdir)
    manager = RunManager(repo)
    series_dir = _find_existing_series(resolved_workdir, series)
    snapshot_id = repo.current_snapshot_id(series_dir.name)
    run = repo.create_run(
        command="write",
        model=model or config.llm.model,
        verbose=_resolve_verbose(config, verbose),
        input_snapshot_id=snapshot_id,
    )
    with manager.side_effect_scope(scope=f"series-{series_dir.name}", run=run, phase="write", wait=wait_lock):
        workflow = _make_workflow(
            repo, run, series_dir.name, config, model, max_review_count, max_summary_review_count, verbose
        )
        result = workflow.write_volume(volume)
        console.print(f"[green]✓[/green] Volume {volume} written (snapshot: {result.selection_snapshot_id})")


@app.command()
def export(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path | None = typer.Option(None, "--workdir", "-w", help="Working directory"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model override"),
    verbose: bool | None = typer.Option(None, "--verbose", "-v", help="Verbose output"),
    wait_lock: bool = typer.Option(False, "--wait-lock", help="Wait for the run lock instead of failing fast on contention"),
):
    """Export manuscript for KDP."""
    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(workdir)
    repo = RunRepository(resolved_workdir)
    manager = RunManager(repo)
    series_dir = _find_existing_series(resolved_workdir, series)
    snapshot_id = repo.current_snapshot_id(series_dir.name)
    run = repo.create_run(
        command="export",
        model=model or config.llm.model,
        verbose=_resolve_verbose(config, verbose),
        input_snapshot_id=snapshot_id,
    )
    with manager.side_effect_scope(scope=f"series-{series_dir.name}", run=run, phase="export", wait=wait_lock):
        workflow = _make_workflow(repo, run, series_dir.name, config, model, None, None, verbose)
        result = workflow.export_volume(volume)
        console.print(f"[green]✓[/green] Exported to {result.get('artifact_id', 'N/A')}")


@app.command()
def status(
    workdir: Path | None = typer.Option(None, "--workdir", "-w", help="Working directory"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
):
    """Show current project status."""
    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(workdir)
    repo = RunRepository(resolved_workdir, read_only=True)
    slugs = [series] if series else [path.name for path in resolved_workdir.iterdir() if path.is_dir() and (repo.series_runtime_root(path.name) / "ledger").exists()]
    report: builtins.list[dict[str, Any]] = []
    for slug in slugs:
        if slug is None:
            continue
        try:
            snapshot_id = repo.current_snapshot_id(slug)
            snapshot = repo.load_snapshot(slug, snapshot_id)
            report.append({"slug": slug, "selection_snapshot_id": snapshot_id, "slots": snapshot.slots})
        except (FileNotFoundError, RuntimeContractError) as exc:
            report.append({"slug": slug, "status": str(sanitize_for_storage(str(exc)))})
    console.print_json(json.dumps(report, ensure_ascii=False))


@app.command()
def resume(
    workdir: Path | None = typer.Option(None, "--workdir", "-w", help="Working directory"),
    series: str = typer.Option(None, "--series", "-s", help="Series slug"),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model override"),
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    max_review_count: int | None = typer.Option(None, "--max-review-count", help="Max review cycles per phase"),
    max_summary_review_count: int | None = typer.Option(None, "--max-summary-review-count", help="Max summary review cycles"),
    verbose: bool | None = typer.Option(None, "--verbose", "-v", help="Verbose output"),
    wait_lock: bool = typer.Option(False, "--wait-lock", help="Wait for the run lock instead of failing fast on contention"),
):
    """Resume from the last completed phase for a series."""
    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(workdir)
    repo = RunRepository(resolved_workdir)
    manager = RunManager(repo)
    series_dir = _find_existing_series(resolved_workdir, series)
    snapshot_id = repo.current_snapshot_id(series_dir.name)
    run = repo.create_run(
        command="resume",
        model=model or config.llm.model,
        verbose=_resolve_verbose(config, verbose),
        input_snapshot_id=snapshot_id,
    )
    with manager.side_effect_scope(scope=f"series-{series_dir.name}", run=run, phase="resume", wait=wait_lock):
        workflow = _make_workflow(
            repo, run, series_dir.name, config, model, max_review_count, max_summary_review_count, verbose
        )
        # Resume by running write/export for the requested volume (plan/design already exist).
        console.print(f"[yellow]▶[/yellow] Resuming volume {volume} (write + export)")
        workflow.write_volume(volume)
        result = workflow.export_volume(volume)
        console.print(f"[green]✓[/green] Resumed: {result.get('artifact_id', 'N/A')}")


@app.command()
def complete(
    keywords: str = typer.Argument(..., help="Series keywords"),
    workdir: Path | None = typer.Option(None, "--workdir", "-w", help="Working directory"),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model override"),
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    max_review_count: int | None = typer.Option(None, "--max-review-count", help="Max review cycles per scene"),
    max_summary_review_count: int | None = typer.Option(None, "--max-summary-review-count", help="Max summary review cycles"),
    verbose: bool | None = typer.Option(None, "--verbose", "-v", help="Verbose output"),
    wait_lock: bool = typer.Option(False, "--wait-lock", help="Wait for the run lock instead of failing fast on contention"),
):
    """Run the full pipeline: plan → design → write → export."""
    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(workdir)
    repo = RunRepository(resolved_workdir)
    manager = RunManager(repo)
    run = repo.create_run(command="plan", model=model or config.llm.model, verbose=_resolve_verbose(config, verbose), input_snapshot_id=None)
    workspace_lock = manager.acquire(scope="workspace", run=run, phase="complete", wait=wait_lock)
    series_lock = None
    try:
        workflow = _make_workflow(repo, run, None, config, model, max_review_count, max_summary_review_count, verbose)
        console.print("[bold]Step 1/4: Plan[/bold]")
        existing = _existing_series_slugs(resolved_workdir)
        plan_attempt, plan = workflow._run_task(
            "plan.series.generate",
            {"keywords": keywords, "existing_slugs": existing},
            reason="generate series plan",
        )
        plan_attempt, plan = workflow._review_and_revise(
            "plan.series", plan, plan_attempt,
            review_values=lambda candidate: {"plan": candidate},
            revise_values=lambda candidate, review: {"current_plan": candidate, "review": review},
            contract_issues=lambda candidate: (
                [] if isinstance(candidate.get("slug"), str) and re.fullmatch(r"[a-z0-9_]{1,40}", candidate["slug"])
                else [{"severity": "error", "category": "contract", "message": "slug must match [a-z0-9_]{1,40}; it is not normalized by runtime"}]
            ),
        )
        slug = plan["slug"]
        series_lock = manager.promote_plan_to_series(
            workspace_lock=workspace_lock, run=run, slug=slug
        )
        canon_seed = BibleFactory.create_seed(plan).model_dump(mode="json")
        workflow.bootstrap_plan(slug=slug, plan=plan, canon_seed=canon_seed, plan_attempt=plan_attempt)
        console.print(f"[green]✓[/green] Plan: {plan.get('title', 'N/A')} (slug: {slug})")

        console.print(f"[bold]Step 2/4: Design (vol {volume})[/bold]")
        workflow.generate_volume_design(volume=volume, plan=plan)
        console.print(f"[green]✓[/green] Design vol {volume}")

        console.print(f"[bold]Step 3/4: Write (vol {volume})[/bold]")
        write_result = workflow.write_volume(volume)
        console.print(f"[green]✓[/green] Write vol {volume} (snapshot: {write_result.selection_snapshot_id})")

        console.print(f"[bold]Step 4/4: Export (vol {volume})[/bold]")
        export_result = workflow.export_volume(volume)
        console.print(f"[green]✓[/green] Export vol {volume}: {export_result.get('artifact_id', 'N/A')}")
    finally:
        if series_lock is not None:
            series_lock.release()
        workspace_lock.release()
@app.command()
def doctor(
    workdir: Path | None = typer.Option(None, "--workdir", "-w", help="Working directory"),
    model: str | None = typer.Option(None, "--model", "-m", help="Model override to test"),
    ollama_host: str | None = typer.Option(None, "--ollama-host", help="Ollama host override"),
):
    """Diagnose Ollama connectivity and model readiness."""
    resolved_model, resolved_host = _resolve_doctor_defaults(workdir, model, ollama_host)
    cmd_doctor(resolved_model, resolved_host)


@app.command()
def list(
    workdir: Path | None = typer.Option(None, "--workdir", "-w", help="Working directory"),
):
    """List all series in the working directory."""

    table = Table(title="NovelForge Series")
    table.add_column("Slug", style="bold")
    table.add_column("Title")
    table.add_column("Volumes")
    table.add_column("Status")

    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(workdir)
    repo = RunRepository(resolved_workdir, read_only=True)
    for d in sorted(resolved_workdir.iterdir()):
        if not d.is_dir() or d.name.startswith(".") or not repo.ledger_root(d.name).is_dir():
            continue
        try:
            snapshot_id = repo.current_snapshot_id(d.name)
            plan = _selected_payload(repo, d.name, snapshot_id, "plan.series")
            slug = str(plan.get("slug", d.name))
            title = str(plan.get("title", "?"))
            volumes = len(plan.get("planned_volumes", []))
            table.add_row(slug, title, str(volumes), "snapshot-managed")
        except (FileNotFoundError, RuntimeContractError) as exc:
            _log.warning("Failed to read selected plan while listing %s: %s", d.name, exc)

    console.print(table)


runs_app = typer.Typer(help="Read-only run inspection")
run_app = typer.Typer(help="Read-only run inspection")
attempt_app = typer.Typer(help="Read-only attempt inspection")
llm_app = typer.Typer(help="Read-only LLM comparisons")
artifact_app = typer.Typer(help="Read-only artifact comparisons")
app.add_typer(runs_app, name="runs")
app.add_typer(run_app, name="run")
app.add_typer(attempt_app, name="attempt")
app.add_typer(llm_app, name="llm")
app.add_typer(artifact_app, name="artifact")


def _readonly_repo(workdir: Path | None) -> RunRepository:
    return RunRepository(RuntimeConfig.load().resolve_workdir(workdir), read_only=True)


@runs_app.command("active")
def runs_active(workdir: Path | None = typer.Option(None, "--workdir", "-w")) -> None:
    """List active locks without creating a run or changing repository state."""
    repo = _readonly_repo(workdir)
    locks = repo.runtime_root / "locks"
    active = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(locks.glob("*.lock.json"))] if locks.exists() else []
    console.print_json(json.dumps(active, ensure_ascii=False))


@run_app.command("show")
def run_show(run_id: str, workdir: Path | None = typer.Option(None, "--workdir", "-w")) -> None:
    """Show one immutable run manifest and append-only event stream."""
    repo = _readonly_repo(workdir)
    run = repo.read_run(run_id)
    events = (run.path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    console.print_json(json.dumps({"run": run.manifest.model_dump(), "events": [json.loads(line) for line in events if line]}, ensure_ascii=False))


@attempt_app.command("show")
def attempt_show(attempt_id: str, workdir: Path | None = typer.Option(None, "--workdir", "-w")) -> None:
    """Show immutable attempt metadata and its files."""
    repo = _readonly_repo(workdir)
    attempt = repo.read_attempt(attempt_id)
    payload = {"attempt": attempt.manifest.model_dump(), "files": sorted(str(path.relative_to(attempt.path)) for path in attempt.path.rglob("*") if path.is_file())}
    console.print_json(json.dumps(payload, ensure_ascii=False))


@llm_app.command("diff")
def llm_diff(attempt_a: str, attempt_b: str, metadata_only: bool = typer.Option(False, "--metadata-only"), workdir: Path | None = typer.Option(None, "--workdir", "-w")) -> None:
    """Diff two attempts; full diff requires complete verbose capture."""
    console.print(_readonly_repo(workdir).llm_diff(attempt_a, attempt_b, metadata_only=metadata_only))


@artifact_app.command("diff")
def artifact_diff(artifact_a: str, artifact_b: str, workdir: Path | None = typer.Option(None, "--workdir", "-w")) -> None:
    """Diff two verified immutable artifact payloads."""
    console.print(_readonly_repo(workdir).artifact_diff(artifact_a, artifact_b))


if __name__ == "__main__":
    app()