"""MyCareersFuture CLI - Search Singapore job listings from your terminal."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import box
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from mcf.lib import (
    CATEGORIES,
    CrawlResult,
    Crawler,
    MCFClient,
    console,
    display_job_detail,
    display_job_table,
    err_console,
    find_categories,
    make_progress_table,
)
from mcf.lib.api.client import MCFClientError
from mcf.lib.crawler.crawler import CrawlProgress

# Initialize Typer app
app = typer.Typer(
    name="mcf",
    help="🇸🇬 MyCareersFuture CLI - Search Singapore job listings",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.command()
def search(
    keywords: Annotated[
        Optional[str],
        typer.Argument(help="Search keywords (job title, skills, company)"),
    ] = None,
    page: Annotated[
        int,
        typer.Option("--page", "-p", help="Page number (starts at 0)"),
    ] = 0,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Results per page (max 100)"),
    ] = 100,
    category: Annotated[
        Optional[list[str]],
        typer.Option("--category", "-c", help="Filter by category (can use multiple)"),
    ] = None,
    sort_by_date: Annotated[
        bool,
        typer.Option("--newest", "-n", help="Sort by posting date (newest first)"),
    ] = False,
    show_urls: Annotated[
        bool,
        typer.Option("--urls", "-u", help="Show job URLs in table"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output raw JSON"),
    ] = False,
) -> None:
    """🔍 Search for jobs on MyCareersFuture.

    Examples:

        mcf search "python developer"

        mcf search --page 2 --limit 50

        mcf search "data engineer" --urls

        mcf search --category "Information Technology" --newest

        mcf search -c "Engineering" -c "Manufacturing" -n
    """
    # Validate categories
    validated_categories: list[str] | None = None
    if category:
        validated_categories = []
        for cat in category:
            matches = find_categories(cat)
            if not matches:
                err_console.print(f"[yellow]Warning:[/yellow] Unknown category '{cat}'")
                err_console.print("[dim]Use 'mcf categories' to see available categories[/dim]")
            elif len(matches) == 1:
                validated_categories.append(matches[0])
            else:
                # Exact match takes precedence
                exact = [m for m in matches if m.lower() == cat.lower()]
                if exact:
                    validated_categories.append(exact[0])
                else:
                    validated_categories.append(matches[0])
                    if len(matches) > 1:
                        err_console.print(
                            f"[dim]'{cat}' matched multiple categories, using '{matches[0]}'[/dim]"
                        )

    try:
        with console.status("[cyan]Searching jobs...[/cyan]", spinner="dots"):
            client = MCFClient()
            response = client.search_jobs(
                keywords=keywords,
                page=page,
                limit=limit,
                categories=validated_categories,
                sort_by_date=sort_by_date,
            )
            client.close()

        if json_output:
            console.print_json(response.model_dump_json(by_alias=True))
            return

        if not response.results:
            console.print("[yellow]No jobs found matching your criteria.[/yellow]")
            raise typer.Exit(0)

        display_job_table(response, show_url=show_urls)

        # Pagination info
        total_pages = (response.total + limit - 1) // limit
        console.print(
            f"  [dim]Page {page + 1} of {total_pages:,} "
            f"• Showing {len(response.results)} of {response.total:,} jobs[/dim]"
        )
        if page + 1 < total_pages:
            console.print(f"  [dim]Use [bold]--page {page + 1}[/bold] to see more[/dim]")
        console.print()

    except MCFClientError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@app.command()
def categories(
    search_term: Annotated[
        Optional[str],
        typer.Argument(help="Filter categories by name"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
) -> None:
    """📂 List available job categories.

    Categories can be used with the --category option in search and crawl commands.

    Examples:

        mcf categories

        mcf categories tech

        mcf categories --json
    """
    cats = CATEGORIES if not search_term else find_categories(search_term)

    if json_output:
        console.print_json(json.dumps(cats))
        return

    if not cats:
        console.print(f"[yellow]No categories matching '{search_term}'[/yellow]")
        raise typer.Exit(0)

    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Category", style="white")

    for i, cat in enumerate(cats, 1):
        table.add_row(str(i), cat)

    console.print()
    console.print(
        Panel(
            table,
            title="[bold]📂 Job Categories[/bold]",
            subtitle=f"[dim]{len(cats)} categories[/dim]",
            border_style="blue",
        )
    )
    console.print()


@app.command()
def metadata(
    list_type: Annotated[
        str,
        typer.Argument(
            help="Type of metadata: employment-types, ssoc, ssic, countries, education"
        ),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output raw JSON"),
    ] = False,
    search_term: Annotated[
        Optional[str],
        typer.Option("--search", "-s", help="Filter results by search term"),
    ] = None,
) -> None:
    """📚 View reference data (employment types, classifications, etc.).

    Available types:

    • employment-types - Types of employment (Full Time, Part Time, etc.)

    • ssoc - Singapore Standard Occupational Classification

    • ssic - Singapore Standard Industrial Classification

    • countries - List of countries

    • education - Educational qualifications (SSEC EQA)

    • fields - Fields of study (SSEC FOS)

    Examples:

        mcf metadata employment-types

        mcf metadata ssoc --search engineer

        mcf metadata countries --json
    """
    type_map = {
        "employment-types": "employment_types",
        "ssoc": "ssoc_list",
        "ssic": "ssic_list",
        "countries": "countries_list",
        "education": "ssec_eqa_list",
        "fields": "ssec_fos_list",
    }

    if list_type not in type_map:
        err_console.print(
            f"[red]Unknown metadata type:[/red] {list_type}\n"
            f"[dim]Available: {', '.join(type_map.keys())}[/dim]"
        )
        raise typer.Exit(1)

    try:
        with console.status("[cyan]Fetching metadata...[/cyan]", spinner="dots"):
            client = MCFClient()
            metadata_obj = client.get_metadata()
            client.close()

        data = getattr(metadata_obj, type_map[list_type])

        # Filter if search term provided
        if search_term:
            search_lower = search_term.lower()
            filtered = []
            for item in data:
                item_dict = item.model_dump()
                if any(search_lower in str(v).lower() for v in item_dict.values()):
                    filtered.append(item)
            data = filtered

        if json_output:
            console.print_json(json.dumps([item.model_dump(by_alias=True) for item in data]))
            return

        if not data:
            console.print("[yellow]No results found.[/yellow]")
            raise typer.Exit(0)

        # Display in table
        table = Table(
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
            expand=True,
        )

        # Add columns based on type
        sample = data[0].model_dump()
        for key in sample:
            table.add_column(key.replace("_", " ").title())

        for item in data:
            values = item.model_dump()
            table.add_row(*[str(v) for v in values.values()])

        title_display = list_type.replace("-", " ").title()
        console.print()
        console.print(
            Panel(
                table,
                title=f"[bold]📚 {title_display}[/bold]",
                subtitle=f"[dim]{len(data)} items[/dim]",
                border_style="green",
            )
        )
        console.print()

    except MCFClientError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@app.command()
def job(
    job_id: Annotated[
        str,
        typer.Argument(help="Job UUID or MCF Job ID (e.g., MCF-2025-1234567)"),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output raw JSON"),
    ] = False,
) -> None:
    """📄 View details for a specific job.

    Note: This searches for the job by ID in recent listings.
    For full job details, visit the URL shown in search results.

    Example:

        mcf job MCF-2025-1969666
    """
    try:
        with console.status("[cyan]Searching for job...[/cyan]", spinner="dots"):
            client = MCFClient()
            # Search with high limit to find the job
            response = client.search_jobs(limit=100)
            client.close()

        # Find the job by UUID or job_post_id
        found_job = None
        for job_posting in response.results:
            if job_posting.uuid == job_id or job_posting.metadata.job_post_id == job_id:
                found_job = job_posting
                break

        if not found_job:
            console.print(
                f"[yellow]Job '{job_id}' not found in recent listings.[/yellow]\n"
                "[dim]Try searching for specific keywords instead.[/dim]"
            )
            raise typer.Exit(1)

        if json_output:
            console.print_json(found_job.model_dump_json(by_alias=True))
            return

        display_job_detail(found_job)

    except MCFClientError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@app.command()
def stats() -> None:
    """📊 Show current job market statistics."""
    try:
        with console.status("[cyan]Fetching statistics...[/cyan]", spinner="dots"):
            client = MCFClient()
            response = client.search_jobs(limit=1)
            client.close()

        console.print()
        console.print(
            Panel(
                f"[bold green]{response.total:,}[/bold green] active job listings",
                title="[bold]📊 MyCareersFuture Statistics[/bold]",
                border_style="blue",
            )
        )
        console.print()

    except MCFClientError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@app.command()
def crawl(
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output directory for parquet files",
        ),
    ] = Path("data/jobs"),
    batch_size: Annotated[
        int,
        typer.Option(
            "--batch-size",
            "-b",
            help="Jobs per batch before flushing to disk",
        ),
    ] = 1000,
    crawl_date_override: Annotated[
        Optional[str],
        typer.Option(
            "--date",
            help="Override crawl date (YYYY-MM-DD format, default: today)",
        ),
    ] = None,
    rate_limit: Annotated[
        float,
        typer.Option(
            "--rate-limit",
            "-r",
            help="API requests per second",
        ),
    ] = 5.0,
    category: Annotated[
        Optional[list[str]],
        typer.Option("--category", "-c", help="Filter by category (can use multiple)"),
    ] = None,
    no_json: Annotated[
        bool,
        typer.Option(
            "--no-json",
            help="Don't save raw JSON files (only parquet)",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Fetch but don't save (for testing)",
        ),
    ] = False,
) -> None:
    """🕷️ Crawl ALL active job postings for historical archival.

    Fetches every job currently on MyCareersFuture and saves to partitioned
    parquet files for time-series analysis. Also saves raw JSON for debugging.

    The crawler:

    • Runs until ALL jobs are fetched (no arbitrary limits)

    • Flushes to disk in batches to keep RAM usage low

    • Writes part files (part-001.parquet, part-001.json.gz, ...)

    • Partitions by date: data/jobs/crawl_date=YYYY-MM-DD/

    • Sorts by posting date (newest first)

    Examples:

        mcf crawl

        mcf crawl --output ./archive --batch-size 2000

        mcf crawl --date 2025-01-15 --dry-run

        mcf crawl --category "Information Technology"

        mcf crawl -c "Engineering" -c "Manufacturing"
    """
    # Parse crawl date
    if crawl_date_override:
        try:
            target_date = date.fromisoformat(crawl_date_override)
        except ValueError:
            err_console.print(f"[red]Invalid date format:[/red] {crawl_date_override}")
            err_console.print("[dim]Use YYYY-MM-DD format[/dim]")
            raise typer.Exit(1)
    else:
        target_date = date.today()

    # Validate categories
    validated_categories: list[str] | None = None
    if category:
        validated_categories = []
        for cat in category:
            matches = find_categories(cat)
            if not matches:
                err_console.print(f"[yellow]Warning:[/yellow] Unknown category '{cat}'")
                err_console.print("[dim]Use 'mcf categories' to see available categories[/dim]")
            elif len(matches) == 1:
                validated_categories.append(matches[0])
            else:
                exact = [m for m in matches if m.lower() == cat.lower()]
                if exact:
                    validated_categories.append(exact[0])
                else:
                    validated_categories.append(matches[0])

    # Build config display
    config_lines = [
        f"[bold]Target Date:[/bold] {target_date}",
        f"[bold]Output:[/bold] {output_dir / f'crawl_date={target_date.isoformat()}'}",
        f"[bold]Batch Size:[/bold] {batch_size:,}",
        f"[bold]Rate Limit:[/bold] {rate_limit} req/s",
        f"[bold]Save JSON:[/bold] {'No' if no_json else 'Yes'}",
    ]
    if validated_categories:
        config_lines.append(f"[bold]Categories:[/bold] {', '.join(validated_categories)}")

    console.print()
    console.print(
        Panel(
            "\n".join(config_lines),
            title="[bold cyan]🕷️ MCF Crawler[/bold cyan]",
            border_style="cyan",
        )
    )
    console.print()

    # Create crawler
    crawler = Crawler(
        output_dir=output_dir,
        batch_size=batch_size,
        rate_limit=rate_limit,
        save_json=not no_json,
        dry_run=dry_run,
    )

    # Get initial count
    try:
        with console.status("[cyan]Counting active jobs...[/cyan]", spinner="dots"):
            client = MCFClient()
            initial = client.search_jobs(limit=1, categories=validated_categories)
            total_jobs = initial.total
            client.close()

        console.print(f"[green]Found {total_jobs:,} active jobs to crawl[/green]")
        console.print()

        # Progress callback
        def on_progress(progress: CrawlProgress) -> None:
            live.update(
                make_progress_table(
                    progress.total_jobs,
                    progress.fetched,
                    progress.saved,
                    progress.elapsed,
                    progress.part_num,
                )
            )

        # Run crawl with live display
        with Live(
            make_progress_table(total_jobs, 0, 0, 0.001, 0),
            console=console,
            refresh_per_second=4,
        ) as live:
            try:
                result = crawler.crawl(
                    categories=validated_categories,
                    target_date=target_date,
                    on_progress=on_progress,
                )
            except KeyboardInterrupt:
                result = CrawlResult(
                    partition_dir=output_dir / f"crawl_date={target_date.isoformat()}",
                    interrupted=True,
                )

        # Final summary
        _display_crawl_result(result)

        if result.interrupted:
            raise typer.Exit(130)

    except MCFClientError as e:
        err_console.print(f"\n[red]Crawl Error:[/red] {e}")
        raise typer.Exit(1) from e


def _display_crawl_result(result: CrawlResult) -> None:
    """Display crawl result summary."""
    if result.interrupted:
        status = "[yellow]⚠️ Crawl Interrupted[/yellow]"
        border = "yellow"
        title = "[bold]📊 Partial Results[/bold]"
    else:
        status = "[bold green]✓ Crawl Complete[/bold green]"
        border = "green"
        title = "[bold]📊 Summary[/bold]"

    console.print()
    console.print(
        Panel(
            f"{status}\n\n"
            f"[bold]Jobs Fetched:[/bold] {result.fetched_count:,}\n"
            f"[bold]Jobs Saved:[/bold] {result.saved_count:,}\n"
            f"[bold]Part Files:[/bold] {result.part_count}\n"
            f"[bold]Duration:[/bold] {result.duration_display}\n"
            f"[bold]Output:[/bold] {result.partition_dir}",
            title=title,
            border_style=border,
        )
    )
    console.print()


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
