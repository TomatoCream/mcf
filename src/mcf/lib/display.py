"""Display and formatting utilities for CLI output."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from mcf.lib.models.models import JobPosting, JobSearchResponse


console = Console()
err_console = Console(stderr=True)


def format_salary(job: JobPosting) -> str:
    """Format salary with color based on range."""
    if job.salary is None:
        return "[dim]Not disclosed[/dim]"
    if job.metadata.is_hide_salary:
        return "[dim]Hidden[/dim]"
    return f"[green]{job.salary.display}[/green]"


def format_employment_types(job: JobPosting) -> str:
    """Format employment types."""
    if not job.employment_types:
        return "[dim]-[/dim]"
    return ", ".join(et.employment_type for et in job.employment_types)


def truncate(text: str, max_len: int = 40) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def display_job_table(response: JobSearchResponse, *, show_url: bool = False) -> None:
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
            truncate(job.title, 45),
            truncate(job.company_name, 30),
            format_salary(job),
            truncate(format_employment_types(job), 15),
            truncate(job.location, 20),
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
            title="[bold]🔍 Job Search Results[/bold]",
            subtitle=str(header),
            border_style="blue",
        )
    )
    console.print()


def display_job_detail(job: JobPosting) -> None:
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

    details.add_row("💰 Salary", format_salary(job))
    details.add_row("📍 Location", job.location)
    details.add_row("📋 Type", format_employment_types(job))

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
    details.add_row(
        "🔗 URL",
        f"[link={job.metadata.job_details_url}]{job.metadata.job_details_url}[/link]",
    )

    console.print(details)
    console.print()


def make_progress_table(
    total_jobs: int,
    fetched: int,
    saved: int,
    elapsed: float,
    part_num: int,
) -> Table:
    """Create a live progress table for crawling."""
    table = Table(box=box.ROUNDED, show_header=False, border_style="cyan")
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="bold")

    speed = fetched / elapsed if elapsed > 0 else 0
    eta_seconds = (total_jobs - fetched) / speed if speed > 0 else 0
    eta_min = int(eta_seconds // 60)
    eta_sec = int(eta_seconds % 60)

    table.add_row("📊 Active Jobs", f"[green]{total_jobs:,}[/green]")
    table.add_row("📥 Fetched", f"[cyan]{fetched:,}[/cyan]")
    table.add_row("💾 Saved", f"[yellow]{saved:,}[/yellow]")
    table.add_row("📁 Part Files", f"[magenta]{part_num}[/magenta]")
    table.add_row("⚡ Speed", f"[blue]{speed:.1f} jobs/sec[/blue]")
    table.add_row("⏱️  ETA", f"[dim]{eta_min}m {eta_sec}s[/dim]")

    pct = (fetched / total_jobs * 100) if total_jobs > 0 else 0
    table.add_row("📈 Progress", f"[bold green]{pct:.1f}%[/bold green]")

    return table

