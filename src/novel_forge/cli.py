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
) -> NovelEngine:
    return NovelEngine(workdir=workdir, model=model, lang=lang, max_review_retries=max_review_retries)


@app.command()
def plan(
    keywords: str = typer.Argument(..., help="Series keywords"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option("qwen3.6:35b-a3b-mtp-q4_K_M", "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
):
    """Generate a series plan from keywords."""
    engine = _engine(workdir, model, lang)
    result = engine.plan(keywords)
    console.print(f"[green]✓[/green] Series plan generated: {result.get('title', 'N/A')}")


@app.command()
def outline(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option("qwen3.6:35b-a3b-mtp-q4_K_M", "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
):
    """Generate a volume outline."""
    engine = _engine(workdir, model, lang)
    result = engine.outline(volume)
    console.print(f"[green]✓[/green] Volume {volume} outline generated")


@app.command()
def write(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option("qwen3.6:35b-a3b-mtp-q4_K_M", "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    max_retries: int = typer.Option(2, "--max-retries", help="Max review retries per scene"),
):
    """Write scene drafts."""
    engine = _engine(workdir, model, lang, max_review_retries=max_retries)
    results = engine.write(volume)
    console.print(f"[green]✓[/green] {len(results)} scenes processed")


@app.command()
def export(
    volume: int = typer.Option(1, "--volume", "-V", help="Volume number"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option("qwen3.6:35b-a3b-mtp-q4_K_M", "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
):
    """Export manuscript for KDP."""
    engine = _engine(workdir, model, lang)
    result = engine.export(volume)
    console.print(f"[green]✓[/green] Exported to {result['manuscript_path']}")


@app.command()
def status(
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option("qwen3.6:35b-a3b-mtp-q4_K_M", "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
):
    """Show current project status."""
    engine = _engine(workdir, model, lang)
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
):
    """Resume from the last interrupted phase."""
    engine = _engine(workdir, model, lang)
    result = engine.resume()
    action = result["action"]
    console.print(f"[yellow]▶[/yellow] Resume: {action} (status: {result['status']})")
    if action == "write":
        engine.write()
    elif action == "outline":
        engine.outline()
    elif action == "export":
        engine.export()


@app.command()
def complete(
    keywords: str = typer.Argument(..., help="Series keywords"),
    workdir: Path = typer.Option(Path("."), "--workdir", "-w", help="Working directory"),
    model: str = typer.Option("qwen3.6:35b-a3b-mtp-q4_K_M", "--model", "-m", help="LLM model"),
    lang: str = typer.Option("ja", "--lang", help="Output language"),
    max_retries: int = typer.Option(2, "--max-retries", help="Max review retries per scene"),
):
    """Run the full pipeline: plan → outline → write → export."""
    engine = _engine(workdir, model, lang, max_review_retries=max_retries)
    console.print("[bold]Step 1/4: Plan[/bold]")
    engine.plan(keywords)
    console.print("[bold]Step 2/4: Outline[/bold]")
    engine.outline()
    console.print("[bold]Step 3/4: Write[/bold]")
    engine.write()
    console.print("[bold]Step 4/4: Export[/bold]")
    result = engine.export()
    console.print(f"[green]✓[/green] Complete! Manuscript: {result['manuscript_path']}")


if __name__ == "__main__":
    app()
