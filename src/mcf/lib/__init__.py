"""MCF library module."""

from mcf.lib.api.client import MCFClient
from mcf.lib.categories import CATEGORIES, find_categories, get_categories, validate_category
from mcf.lib.crawler import CrawlResult, Crawler
from mcf.lib.display import (
    console,
    display_job_detail,
    display_job_table,
    err_console,
    format_employment_types,
    format_salary,
    make_progress_table,
    truncate,
)
from mcf.lib.models.models import (
    CommonMetadata,
    JobPosting,
    JobSearchResponse,
)
from mcf.lib.serialization import flatten_job

__all__ = [
    # Client
    "MCFClient",
    # Models
    "CommonMetadata",
    "JobPosting",
    "JobSearchResponse",
    # Crawler
    "Crawler",
    "CrawlResult",
    # Categories
    "CATEGORIES",
    "find_categories",
    "get_categories",
    "validate_category",
    # Display
    "console",
    "err_console",
    "display_job_detail",
    "display_job_table",
    "format_employment_types",
    "format_salary",
    "make_progress_table",
    "truncate",
    # Serialization
    "flatten_job",
]

