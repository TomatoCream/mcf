"""MyCareersFuture CLI - Search Singapore job listings from your terminal."""

from __future__ import annotations

from typing import Annotated, Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from mcf.lib.api.client import MCFClient, MCFClientError
from mcf.lib.models.models import JobPosting, JobSearchResponse

# Initialize Typer app
app = typer.Typer(
    name="mcf",
    help="🇸🇬 MyCareersFuture CLI - Search Singapore job listings",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()
err_console = Console(stderr=True)


def _format_salary(job: JobPosting) -> str:
    """Format salary with color based on range."""
    if job.salary is None:
        return "[dim]Not disclosed[/dim]"
    if job.metadata.is_hide_salary:
        return "[dim]Hidden[/dim]"
    return f"[green]{job.salary.display}[/green]"


def _format_employment_types(job: JobPosting) -> str:
    """Format employment types."""
    if not job.employment_types:
        return "[dim]-[/dim]"
    return ", ".join(et.employment_type for et in job.employment_types)


def _truncate(text: str, max_len: int = 40) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _display_job_table(response: JobSearchResponse, *, show_url: bool = False) -> None:
    """Display jobs in a rich table."""
    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        row_styles=["", "dim"],
        expand=True,
    )

    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Title", style="bold white", min_width=25, max_width=45)
    table.add_column("Company", min_width=15, max_width=30)
    table.add_column("Salary", justify="right", min_width=12)
    table.add_column("Type", min_width=10)
    table.add_column("Location", min_width=15)
    if show_url:
        table.add_column("URL", overflow="fold")

    for i, job in enumerate(response.results, 1):
        row = [
            str(i),
            _truncate(job.title, 45),
            _truncate(job.company_name, 30),
            _format_salary(job),
            _truncate(_format_employment_types(job), 15),
            _truncate(job.location, 20),
        ]
        if show_url:
            row.append(job.metadata.job_details_url)
        table.add_row(*row)

    # Header with search stats
    header = Text()
    header.append("Found ", style="dim")
    header.append(f"{response.total:,}", style="bold green")
    header.append(" jobs", style="dim")

    console.print()
    console.print(
        Panel(
            table,
            title=f"[bold]🔍 Job Search Results[/bold]",
            subtitle=str(header),
            border_style="blue",
        )
    )
    console.print()


def _display_job_detail(job: JobPosting) -> None:
    """Display detailed job information."""
    console.print()

    # Title panel
    title_text = Text()
    title_text.append(job.title, style="bold white")
    title_text.append("\n")
    title_text.append(job.company_name, style="cyan")

    console.print(Panel(title_text, border_style="blue"))

    # Details table
    details = Table(show_header=False, box=None, padding=(0, 2))
    details.add_column("Field", style="dim")
    details.add_column("Value")

    details.add_row("💰 Salary", _format_salary(job))
    details.add_row("📍 Location", job.location)
    details.add_row("📋 Type", _format_employment_types(job))

    if job.position_levels:
        levels = ", ".join(pl.position for pl in job.position_levels)
        details.add_row("📊 Level", levels)

    if job.categories:
        cats = ", ".join(c.category for c in job.categories)
        details.add_row("🏷️  Category", cats)

    if job.skills:
        skills = ", ".join(s.skill for s in job.skills[:5])
        if len(job.skills) > 5:
            skills += f" (+{len(job.skills) - 5} more)"
        details.add_row("🛠️  Skills", skills)

    details.add_row("📅 Posted", str(job.metadata.new_posting_date))
    details.add_row("🔗 URL", f"[link={job.metadata.job_details_url}]{job.metadata.job_details_url}[/link]")

    console.print(details)
    console.print()


@app.command()
def search(
    keywords: Annotated[
        Optional[str],
        typer.Argument(help="Search keywords (job title, skills, company)"),
    ] = None,
    salary_min: Annotated[
        Optional[int],
        typer.Option("--min", "-m", help="Minimum monthly salary"),
    ] = None,
    salary_max: Annotated[
        Optional[int],
        typer.Option("--max", "-M", help="Maximum monthly salary"),
    ] = None,
    page: Annotated[
        int,
        typer.Option("--page", "-p", help="Page number (starts at 0)"),
    ] = 0,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Results per page (max 100)"),
    ] = 20,
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

        mcf search --min 5000 --max 10000

        mcf search "data engineer" --min 8000 --urls
    """
    try:
        with console.status("[cyan]Searching jobs...[/cyan]", spinner="dots"):
            client = MCFClient()
            response = client.search_jobs(
                keywords=keywords,
                salary_min=salary_min,
                salary_max=salary_max,
                page=page,
                limit=limit,
            )
            client.close()

        if json_output:
            console.print_json(response.model_dump_json(by_alias=True))
            return

        if not response.results:
            console.print("[yellow]No jobs found matching your criteria.[/yellow]")
            raise typer.Exit(0)

        _display_job_table(response, show_url=show_urls)

        # Pagination info
        total_pages = (response.total + limit - 1) // limit
        console.print(
            f"  [dim]Page {page + 1} of {total_pages:,} "
            f"• Showing {len(response.results)} of {response.total:,} jobs[/dim]"
        )
        if page + 1 < total_pages:
            console.print(
                f"  [dim]Use [bold]--page {page + 1}[/bold] to see more[/dim]"
            )
        console.print()

    except MCFClientError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


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
                if any(
                    search_lower in str(v).lower()
                    for v in item_dict.values()
                ):
                    filtered.append(item)
            data = filtered

        if json_output:
            import json

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
            if (
                job_posting.uuid == job_id
                or job_posting.metadata.job_post_id == job_id
            ):
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

        _display_job_detail(found_job)

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


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()

