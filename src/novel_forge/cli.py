from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from novel_forge.engine import NovelEngine

app = typer.Typer(help="NovelForge — Local-LLM novel production pipeline")
console = Console()


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
    engine = _engine(workdir, model, lang, verbose=verbose)
    result = engine.export(volume)
    console.print(f"[green]✓[/green] Exported to {result['manuscript_path']}")


@app.command()
def status(
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option("qwen3.6:35b-a3b-mtp-q4_K_M", "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
):
    """Show current project status."""
    engine = _engine(workdir, model, lang, verbose=verbose)
    s = engine.status()
    table = Table(title="NovelForge Status")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    for k, v in s.items():
        table.add_row(k, str(v))
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
