"""MCF CLI - Command line interface for MyCareersFuture job crawler."""

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import polars as pl
import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from mcf.lib.crawler.crawler import CrawlProgress, Crawler
from mcf.lib.embeddings.embedder import Embedder, EmbedderConfig
from mcf.lib.embeddings.resume import extract_resume_text
from mcf.lib.pipeline.incremental_crawl import run_incremental_crawl
from mcf.lib.storage.duckdb_store import DuckDBStore

app = typer.Typer(
    name="mcf",
    help="MyCareersFuture job crawler CLI",
    rich_markup_mode="rich",
    invoke_without_command=True,
)


@app.callback()
def callback(ctx: typer.Context) -> None:
    """MyCareersFuture job crawler CLI."""
    if ctx.invoked_subcommand is None:
        raise typer.Exit(ctx.get_help())
console = Console()


@app.command("crawl")
def crawl(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output directory for parquet files",
        ),
    ] = Path("data/jobs"),
    rate_limit: Annotated[
        float,
        typer.Option(
            "--rate-limit",
            "-r",
            help="API requests per second",
        ),
    ] = 4.0,
    limit: Annotated[
        Optional[int],
        typer.Option(
            "--limit",
            "-l",
            help="Maximum number of jobs to fetch (for testing)",
        ),
    ] = None,
) -> None:
    """Crawl all jobs from MyCareersFuture and save to parquet."""
    today = date.today()
    output_dir = output.resolve()

    console.print(f"[bold cyan]MCF Crawler[/bold cyan]")
    console.print(f"  Output: [green]{output_dir}[/green]")
    console.print(f"  Rate limit: [yellow]{rate_limit}[/yellow] req/s")
    if limit:
        console.print(f"  Limit: [yellow]{limit}[/yellow] jobs")
    console.print()

    crawler = Crawler(rate_limit=rate_limit)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Crawling...", total=None)

        def on_progress(p: CrawlProgress) -> None:
            progress.update(task, total=p.total_jobs, completed=p.fetched)
            if p.current_category:
                progress.update(
                    task,
                    description=f"[cyan]{p.current_category}[/cyan] ({p.category_index}/{p.total_categories})",
                )

        if limit:
            # Use simple crawl for testing with limit
            result = crawler.crawl(on_progress=on_progress, limit=limit)
        else:
            result = crawler.crawl_all_categories(on_progress=on_progress)

    # Convert to polars DataFrame
    df = pl.from_pandas(result.jobs)

    # Add crawl_date and delete_date columns
    df = df.with_columns(
        pl.lit(today).alias("crawl_date"),
        pl.lit(None).cast(pl.Date).alias("delete_date"),
    )

    # Use native partition_by for hive-style partitioning
    # This writes to output_dir and creates crawl_date=YYYY-MM-DD/ subdirectories automatically
    df.write_parquet(
        str(output_dir),
        partition_by=["crawl_date"],
        compression="zstd",
        compression_level=10,
    )

    # Print summary
    console.print()
    if result.interrupted:
        console.print("[yellow]⚠ Crawl was interrupted[/yellow]")

    console.print(f"[bold green]✓ Crawl complete[/bold green]")
    console.print(f"  Jobs fetched: [cyan]{result.fetched_count:,}[/cyan]")
    console.print(f"  Duration: [cyan]{result.duration_display}[/cyan]")
    console.print(f"  Output: [green]{output_dir}[/green]")


@app.command("crawl-incremental")
def crawl_incremental(
    db: Annotated[
        Path,
        typer.Option(
            "--db",
            help="DuckDB file path for incremental state",
        ),
    ] = Path("data/mcf.duckdb"),
    rate_limit: Annotated[
        float,
        typer.Option(
            "--rate-limit",
            "-r",
            help="API requests per second",
        ),
    ] = 4.0,
    limit: Annotated[
        Optional[int],
        typer.Option(
            "--limit",
            "-l",
            help="Maximum number of jobs to list (for testing)",
        ),
    ] = None,
    categories: Annotated[
        Optional[str],
        typer.Option(
            "--categories",
            help="Comma-separated category names (default: all categories)",
        ),
    ] = None,
) -> None:
    """Incrementally crawl jobs into DuckDB (fetch job detail only for newly-seen UUIDs)."""
    console.print(f"[bold cyan]MCF Incremental Crawler[/bold cyan]")
    console.print(f"  DB: [green]{db.resolve()}[/green]")
    console.print(f"  Rate limit: [yellow]{rate_limit}[/yellow] req/s")
    if limit:
        console.print(f"  Limit: [yellow]{limit}[/yellow] jobs")
    if categories:
        console.print(f"  Categories: [yellow]{categories}[/yellow]")
    console.print()

    cats = [c.strip() for c in categories.split(",") if c.strip()] if categories else None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Listing UUIDs...", total=None)

        def on_progress(p: CrawlProgress) -> None:
            progress.update(task, total=p.total_jobs, completed=p.fetched)
            if p.current_category:
                progress.update(
                    task,
                    description=f"[cyan]{p.current_category}[/cyan] ({p.category_index}/{p.total_categories})",
                )

        result = run_incremental_crawl(
            db_path=db,
            rate_limit=rate_limit,
            categories=cats,
            limit=limit,
            on_progress=on_progress,
        )

    console.print()
    # Avoid Unicode checkmark which can crash on legacy Windows terminals (cp1252).
    console.print("[bold green]Incremental crawl complete[/bold green]")
    console.print(f"  Total seen: [cyan]{result.total_seen:,}[/cyan]")
    console.print(f"  Added: [cyan]{len(result.added):,}[/cyan]")
    console.print(f"  Maintained: [cyan]{len(result.maintained):,}[/cyan]")
    console.print(f"  Removed: [cyan]{len(result.removed):,}[/cyan]")


@app.command("embed-jobs")
def embed_jobs(
    db: Annotated[
        Path,
        typer.Option(
            "--db",
            help="DuckDB file path for incremental state",
        ),
    ] = Path("data/mcf.duckdb"),
    model: Annotated[
        str,
        typer.Option(
            "--model",
            help="SentenceTransformers model name",
        ),
    ] = "sentence-transformers/all-MiniLM-L6-v2",
    limit: Annotated[
        Optional[int],
        typer.Option(
            "--limit",
            "-l",
            help="Maximum number of jobs to embed (for testing)",
        ),
    ] = None,
) -> None:
    """Embed active jobs missing embeddings and store vectors in DuckDB."""
    console.print(f"[bold cyan]MCF Embed Jobs[/bold cyan]")
    console.print(f"  DB: [green]{db.resolve()}[/green]")
    console.print(f"  Model: [yellow]{model}[/yellow]")
    if limit:
        console.print(f"  Limit: [yellow]{limit}[/yellow]")
    console.print()

    store = DuckDBStore(db)
    try:
        missing = store.jobs_missing_embeddings(limit=limit)
        if not missing:
            console.print("[green]No missing embeddings found (nothing to do).[/green]")
            return

        embedder = Embedder(EmbedderConfig(model_name=model))
        texts = [desc or "" for _, desc in missing]
        vectors = embedder.embed_texts(texts)

        for (job_uuid, _), vec in zip(missing, vectors, strict=True):
            store.upsert_embedding(job_uuid=job_uuid, model_name=embedder.model_name, embedding=vec)

        console.print("[bold green]Embeddings stored[/bold green]")
        console.print(f"  Embedded: [cyan]{len(missing):,}[/cyan] jobs")
    finally:
        store.close()


@app.command("match-resume")
def match_resume(
    resume: Annotated[
        Path,
        typer.Argument(help="Resume file path (.pdf, .docx, .txt, .md)"),
    ],
    db: Annotated[
        Path,
        typer.Option(
            "--db",
            help="DuckDB file path for incremental state",
        ),
    ] = Path("data/mcf.duckdb"),
    model: Annotated[
        str,
        typer.Option(
            "--model",
            help="SentenceTransformers model name (must match job embeddings model)",
        ),
    ] = "sentence-transformers/all-MiniLM-L6-v2",
    top: Annotated[
        int,
        typer.Option(
            "--top",
            help="Number of top matches to show",
        ),
    ] = 25,
) -> None:
    """Embed a resume and rank active jobs by cosine similarity to job embeddings."""
    text = extract_resume_text(resume)
    if not text.strip():
        raise typer.BadParameter("Resume text extraction produced empty content.")

    embedder = Embedder(EmbedderConfig(model_name=model))
    resume_vec = embedder.embed_text(text)

    # Lazy import to keep base CLI light.
    import numpy as np  # type: ignore

    store = DuckDBStore(db)
    try:
        jobs = store.get_active_job_embeddings()
        if not jobs:
            console.print("[yellow]No active job embeddings found. Run `mcf embed-jobs` first.[/yellow]")
            return

        rv = np.array(resume_vec, dtype=np.float32)
        scored: list[tuple[float, str, str]] = []
        for job_uuid, title, emb in jobs:
            jv = np.array(emb, dtype=np.float32)
            # embeddings are normalized, so dot product == cosine similarity
            score = float(np.dot(rv, jv))
            scored.append((score, job_uuid, title))

        scored.sort(reverse=True, key=lambda x: x[0])
        scored = scored[: max(1, int(top))]

        console.print(f"[bold green]Top {len(scored)} matches[/bold green]")
        for score, job_uuid, title in scored:
            console.print(f"[cyan]{score:0.4f}[/cyan]  {title}  ({job_uuid})")
    finally:
        store.close()


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
