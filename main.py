from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich import print as rprint

app = typer.Typer(help="Local AI repo assistant — ask questions about any codebase.")
console = Console()


def _make_agent(repo: Optional[str]):
    from agent.repo_agent import RepoAgent
    return RepoAgent(repo_path=repo)


@app.command()
def index(
    repo: Annotated[Optional[str], typer.Option("--repo", "-r", help="Path to the repo to index")] = None,
    force: Annotated[bool, typer.Option("--force", help="Wipe existing index and re-index from scratch")] = False,
    file: Annotated[Optional[str], typer.Option("--file", help="Index a single file only")] = None,
):
    """Index a repository so you can ask questions about it."""
    agent = _make_agent(repo)

    if force:
        confirmed = typer.confirm(
            f"This will wipe the entire index for '{agent._collection_name}'. Continue?"
        )
        if not confirmed:
            rprint("[yellow]Aborted.[/yellow]")
            raise typer.Exit()
        agent.clear_index()
        rprint(f"[yellow]Index cleared for '{agent._collection_name}'.[/yellow]")

    repo_display = agent.repo_path
    rprint(f"\n[bold]Indexing:[/bold] {repo_display}")
    rprint(f"[dim]Collection: {agent._collection_name}[/dim]\n")

    indexed_files = []

    def on_progress(fp: str, chunk_count: int):
        rel = Path(fp).relative_to(agent.repo_path) if Path(fp).is_relative_to(agent.repo_path) else fp
        indexed_files.append((str(rel), chunk_count))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Indexing files...", total=None)
        stats = agent.index(progress_callback=on_progress, file_path=file)
        progress.update(task, completed=stats.files_scanned)

    # Summary table
    table = Table(title="Index Complete", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Files scanned", str(stats.files_scanned))
    table.add_row("Files skipped (unchanged)", str(stats.files_skipped))
    table.add_row("Chunks created", str(stats.chunks_created))
    console.print(table)
    rprint(f"\n[green]✓ Done.[/green] Run [bold]python main.py ask \"your question\"[/bold] to query.\n")


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="Question to ask about the codebase")],
    repo: Annotated[Optional[str], typer.Option("--repo", "-r", help="Path to the repo")] = None,
    debug: Annotated[bool, typer.Option("--debug", help="Show retrieved chunks before the answer")] = False,
):
    """Ask a natural language question about the indexed codebase."""
    agent = _make_agent(repo)

    rprint(f"\n[dim]Collection: {agent._collection_name}[/dim]")

    with console.status("[bold green]Retrieving relevant code...[/bold green]", spinner="dots"):
        # Prime the generator — retrieval happens on first iteration
        gen = agent.query(question, debug=debug)
        first_token = next(gen, None)

    if first_token is None:
        rprint("[red]No response.[/red]")
        return

    console.print()
    console.print(first_token, end="", highlight=False)
    for token in gen:
        console.print(token, end="", highlight=False)
    console.print("\n")


@app.command()
def stats(
    repo: Annotated[Optional[str], typer.Option("--repo", "-r", help="Path to the repo")] = None,
):
    """Show index statistics for a repository."""
    agent = _make_agent(repo)
    s = agent.stats()

    last = (
        datetime.fromtimestamp(s["last_indexed"]).strftime("%Y-%m-%d %H:%M")
        if s["last_indexed"]
        else "Never"
    )

    table = Table(title=f"Index Stats — {agent._collection_name}", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Total chunks", str(s["total_chunks"]))
    table.add_row("Files indexed", str(s["files_indexed"]))
    table.add_row("Last indexed", last)
    table.add_row("Collection", s["collection"])
    console.print(table)


if __name__ == "__main__":
    app()
