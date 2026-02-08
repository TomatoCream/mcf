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

from mcf.api.services.matching_service import MatchingService
from mcf.lib.crawler.crawler import CrawlProgress, Crawler
from mcf.lib.embeddings.embedder import Embedder, EmbedderConfig
from mcf.lib.embeddings.resume import extract_resume_text
from mcf.lib.pipeline.incremental_crawl import run_incremental_crawl
from mcf.lib.storage.base import Storage
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
        Optional[Path],
        typer.Option(
            "--db",
            help="DuckDB file path (default: data/mcf.duckdb)",
        ),
    ] = None,
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
    """Incrementally crawl jobs (fetch job detail only for newly-seen UUIDs)."""
    # Use DuckDB only
    if db:
        store: Storage = DuckDBStore(db)
        db_display = f"DuckDB: {db.resolve()}"
    else:
        # Default to DuckDB
        default_db = Path("data/mcf.duckdb")
        default_db.parent.mkdir(parents=True, exist_ok=True)
        store = DuckDBStore(default_db)
        db_display = f"DuckDB: {default_db.resolve()}"

    console.print(f"[bold cyan]MCF Incremental Crawler[/bold cyan]")
    console.print(f"  Storage: [green]{db_display}[/green]")
    console.print(f"  Rate limit: [yellow]{rate_limit}[/yellow] req/s")
    if limit:
        console.print(f"  Limit: [yellow]{limit}[/yellow] jobs")
    if categories:
        console.print(f"  Categories: [yellow]{categories}[/yellow]")
    console.print()

    cats = [c.strip() for c in categories.split(",") if c.strip()] if categories else None

    try:
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
                store=store,
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
    finally:
        store.close()


@app.command("process-resume")
def process_resume(
    resume_path: Annotated[
        Path,
        typer.Option(
            "--resume",
            "-r",
            help="Path to resume file (default: resume/resume.pdf)",
        ),
    ] = Path("resume/resume.pdf"),
    user_id: Annotated[
        str,
        typer.Option(
            "--user-id",
            "-u",
            help="User ID (default: default_user)",
        ),
    ] = "default_user",
    db: Annotated[
        Optional[Path],
        typer.Option(
            "--db",
            help="DuckDB file path (default: data/mcf.duckdb)",
        ),
    ] = None,
) -> None:
    """Process resume from file and create profile for matching."""
    db_path = db or Path("data/mcf.duckdb")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = DuckDBStore(db_path)
    
    try:
        if not resume_path.exists():
            console.print(f"[bold red]Error:[/bold red] Resume file not found at {resume_path}")
            console.print(f"Please place your resume file at: {resume_path}")
            raise typer.Exit(1)
        
        console.print(f"[bold cyan]Processing Resume[/bold cyan]")
        console.print(f"  Resume: [green]{resume_path.resolve()}[/green]")
        console.print(f"  User ID: [yellow]{user_id}[/yellow]")
        console.print(f"  Database: [green]{db_path.resolve()}[/green]")
        console.print()
        
        # Extract resume text
        console.print("[cyan]Extracting resume text...[/cyan]")
        resume_text = extract_resume_text(resume_path)
        console.print(f"[green]Extracted {len(resume_text)} characters[/green]")
        
        # Get or create profile
        profile = store.get_profile_by_user_id(user_id)
        if profile:
            profile_id = profile["profile_id"]
            console.print(f"[cyan]Updating existing profile: {profile_id}[/cyan]")
            store.update_profile(profile_id=profile_id, raw_resume_text=resume_text)
        else:
            import secrets
            profile_id = secrets.token_urlsafe(16)
            console.print(f"[cyan]Creating new profile: {profile_id}[/cyan]")
            store.create_profile(
                profile_id=profile_id,
                user_id=user_id,
                raw_resume_text=resume_text,
            )
        
        # Generate embedding directly from resume text
        console.print("[cyan]Generating embedding...[/cyan]")
        embedder = Embedder(EmbedderConfig())
        embedding = embedder.embed_text(resume_text)
        store.upsert_candidate_embedding(
            profile_id=profile_id,
            model_name=embedder.model_name,
            embedding=embedding,
        )
        
        console.print()
        console.print("[bold green]Resume processed successfully![/bold green]")
        console.print(f"  Profile ID: [cyan]{profile_id}[/cyan]")
        console.print(f"  You can now use 'mcf match-jobs' to find matching jobs")
    finally:
        store.close()


@app.command("match-jobs")
def match_jobs(
    user_id: Annotated[
        str,
        typer.Option(
            "--user-id",
            "-u",
            help="User ID (default: default_user)",
        ),
    ] = "default_user",
    top_k: Annotated[
        int,
        typer.Option(
            "--top-k",
            "-k",
            help="Number of top matches to return",
        ),
    ] = 25,
    exclude_interacted: Annotated[
        bool,
        typer.Option(
            "--exclude-interacted/--include-interacted",
            help="Exclude jobs user has interacted with",
        ),
    ] = True,
    db: Annotated[
        Optional[Path],
        typer.Option(
            "--db",
            help="DuckDB file path (default: data/mcf.duckdb)",
        ),
    ] = None,
) -> None:
    """Find matching jobs for uploaded resume."""
    db_path = db or Path("data/mcf.duckdb")
    store = DuckDBStore(db_path)
    
    try:
        # Get profile
        profile = store.get_profile_by_user_id(user_id)
        if not profile:
            console.print(f"[bold red]Error:[/bold red] No profile found for user {user_id}")
            console.print(f"Please run 'mcf process-resume' first")
            raise typer.Exit(1)
        
        profile_id = profile["profile_id"]
        
        console.print(f"[bold cyan]Finding Job Matches[/bold cyan]")
        console.print(f"  User ID: [yellow]{user_id}[/yellow]")
        console.print(f"  Profile ID: [cyan]{profile_id}[/cyan]")
        console.print(f"  Top K: [yellow]{top_k}[/yellow]")
        console.print(f"  Exclude interacted: [yellow]{exclude_interacted}[/yellow]")
        console.print()
        
        # Get matches
        matching_service = MatchingService(store)
        matches = matching_service.match_candidate_to_jobs(
            profile_id=profile_id,
            top_k=top_k,
            exclude_interacted=exclude_interacted,
            user_id=user_id,
        )
        
        if not matches:
            console.print("[yellow]No matches found[/yellow]")
            console.print("Make sure you have:")
            console.print("  1. Processed your resume (mcf process-resume)")
            console.print("  2. Crawled some jobs (mcf crawl-incremental)")
            return
        
        console.print(f"[bold green]Found {len(matches)} matches:[/bold green]")
        console.print()
        
        for i, match in enumerate(matches, 1):
            score = match["similarity_score"]
            title = match["title"] or "N/A"
            company = match.get("company_name") or "N/A"
            location = match.get("location") or "N/A"
            job_url = match.get("job_url") or "N/A"
            
            console.print(f"[bold]{i}. {title}[/bold]")
            console.print(f"   Company: {company}")
            console.print(f"   Location: {location}")
            console.print(f"   Match Score: [green]{score:.2%}[/green]")
            if job_url != "N/A":
                console.print(f"   URL: [blue]{job_url}[/blue]")
            console.print()
    finally:
        store.close()


@app.command("mark-interaction")
def mark_interaction(
    job_uuid: Annotated[
        str,
        typer.Argument(help="Job UUID to mark as interacted"),
    ],
    interaction_type: Annotated[
        str,
        typer.Option(
            "--type",
            "-t",
            help="Interaction type: viewed, dismissed, applied, saved",
        ),
    ],
    user_id: Annotated[
        str,
        typer.Option(
            "--user-id",
            "-u",
            help="User ID (default: default_user)",
        ),
    ] = "default_user",
    db: Annotated[
        Optional[Path],
        typer.Option(
            "--db",
            help="DuckDB file path (default: data/mcf.duckdb)",
        ),
    ] = None,
) -> None:
    """Mark a job as interacted with (viewed, dismissed, applied, etc.)."""
    if interaction_type not in ["viewed", "dismissed", "applied", "saved"]:
        console.print(f"[bold red]Error:[/bold red] Invalid interaction type: {interaction_type}")
        console.print("Valid types: viewed, dismissed, applied, saved")
        raise typer.Exit(1)
    
    db_path = db or Path("data/mcf.duckdb")
    store = DuckDBStore(db_path)
    
    try:
        # Verify job exists
        job = store.get_job(job_uuid)
        if not job:
            console.print(f"[bold red]Error:[/bold red] Job {job_uuid} not found")
            raise typer.Exit(1)
        
        store.record_interaction(user_id=user_id, job_uuid=job_uuid, interaction_type=interaction_type)
        
        console.print(f"[bold green]Interaction recorded[/bold green]")
        console.print(f"  Job: {job.get('title', job_uuid)}")
        console.print(f"  Type: {interaction_type}")
        console.print(f"  User: {user_id}")
    finally:
        store.close()


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
