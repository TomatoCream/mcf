"""Crawler for fetching job postings from MyCareersFuture."""

import time
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from mcf.lib.api.client import MCFClient
from mcf.lib.categories import CATEGORIES
from mcf.lib.models.models import Job


@dataclass
class CategoryResult:
    """Result for a single category crawl."""

    category: str
    """Category name."""

    fetched_count: int = 0
    """Jobs fetched for this category."""

    total_available: int = 0
    """Total jobs available in this category."""

    skipped: bool = False
    """Whether this category was skipped (e.g., 0 jobs)."""


@dataclass
class CrawlResult:
    """Result of a crawl operation."""

    jobs: pd.DataFrame
    """DataFrame containing all fetched jobs."""

    fetched_count: int = 0
    """Total jobs fetched from API."""

    duration_seconds: float = 0
    """Total crawl duration."""

    interrupted: bool = False
    """Whether the crawl was interrupted."""

    category_results: list[CategoryResult] = field(default_factory=list)
    """Per-category results (for all-categories crawl)."""

    @property
    def duration_display(self) -> str:
        """Format duration for display."""
        minutes = int(self.duration_seconds // 60)
        seconds = int(self.duration_seconds % 60)
        return f"{minutes}m {seconds}s"


@dataclass
class CrawlProgress:
    """Current progress of a crawl operation."""

    total_jobs: int
    """Total jobs available to fetch."""

    fetched: int
    """Jobs fetched so far."""

    elapsed: float
    """Elapsed time in seconds."""

    # Category tracking (for all-categories crawl)
    current_category: str | None = None
    """Current category being crawled."""

    category_index: int = 0
    """Current category index (1-indexed)."""

    total_categories: int = 0
    """Total number of categories to crawl."""

    category_fetched: int = 0
    """Jobs fetched in current category."""

    category_total: int = 0
    """Total jobs in current category."""

    @property
    def speed(self) -> float:
        """Jobs per second."""
        return self.fetched / self.elapsed if self.elapsed > 0 else 0

    @property
    def eta_seconds(self) -> float:
        """Estimated seconds remaining."""
        if self.speed <= 0:
            return 0
        return (self.total_jobs - self.fetched) / self.speed

    @property
    def percent_complete(self) -> float:
        """Percentage complete."""
        if self.total_jobs <= 0:
            return 0
        return (self.fetched / self.total_jobs) * 100


type ProgressCallback = Callable[[CrawlProgress], None]


@dataclass
class Crawler:
    """Crawler for fetching all job postings.

    Fetches all jobs from MyCareersFuture and returns them as a DataFrame.

    Example:
        >>> crawler = Crawler()
        >>> result = crawler.crawl(categories=["Information Technology"])
        >>> print(f"Fetched {result.fetched_count} jobs")
        >>> df = result.jobs
    """

    rate_limit: float = 5.0
    """API requests per second."""

    def crawl(
        self,
        *,
        categories: list[str] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> CrawlResult:
        """Crawl all jobs matching the criteria.

        Args:
            categories: Filter by category names (e.g., ["Information Technology"]).
            on_progress: Callback for progress updates.

        Returns:
            CrawlResult with DataFrame of jobs and statistics.
        """
        fetched_count = 0
        jobs_buffer: list[dict] = []
        start_time = time.monotonic()

        try:
            client = MCFClient(rate_limit=self.rate_limit)

            # First request to get total count
            initial_response = client.search_jobs(
                limit=1,
                categories=categories,
                sort_by_date=True,
            )
            total_jobs = initial_response.total

            page = 0
            page_size = 100  # API max

            while True:
                response = client.search_jobs(
                    page=page,
                    limit=page_size,
                    categories=categories,
                    sort_by_date=True,
                )

                if not response.results:
                    break

                for job in response.results:
                    jobs_buffer.append(job.model_dump(by_alias=True, mode="json"))
                    fetched_count += 1

                    if on_progress:
                        elapsed = time.monotonic() - start_time
                        on_progress(
                            CrawlProgress(
                                total_jobs=total_jobs,
                                fetched=fetched_count,
                                elapsed=elapsed,
                            )
                        )

                if (page + 1) * page_size >= response.total:
                    break

                page += 1

            client.close()

            return CrawlResult(
                jobs=pd.DataFrame(jobs_buffer),
                fetched_count=fetched_count,
                duration_seconds=time.monotonic() - start_time,
            )

        except KeyboardInterrupt:
            return CrawlResult(
                jobs=pd.DataFrame(jobs_buffer),
                fetched_count=fetched_count,
                duration_seconds=time.monotonic() - start_time,
                interrupted=True,
            )

    def crawl_all_categories(
        self,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> CrawlResult:
        """Crawl all categories to get around the 10k pagination limit.

        The API limits pagination to ~10k results. By crawling each category
        separately, we can get all jobs even when total exceeds 10k.

        Args:
            on_progress: Callback for progress updates.

        Returns:
            CrawlResult with DataFrame of jobs and statistics.
        """
        fetched_count = 0
        seen_uuids: set[str] = set()
        jobs_buffer: list[dict] = []
        category_results: list[CategoryResult] = []
        start_time = time.monotonic()

        try:
            client = MCFClient(rate_limit=self.rate_limit)

            # First, count jobs per category to estimate total
            category_counts: list[tuple[str, int]] = []
            for cat in CATEGORIES:
                response = client.search_jobs(limit=1, categories=[cat])
                category_counts.append((cat, response.total))

            estimated_total = sum(count for _, count in category_counts)
            total_categories = len(CATEGORIES)

            for cat_idx, (category, cat_total) in enumerate(category_counts, 1):
                cat_result = CategoryResult(
                    category=category,
                    total_available=cat_total,
                )

                if cat_total == 0:
                    cat_result.skipped = True
                    category_results.append(cat_result)
                    continue

                cat_fetched = 0
                page = 0
                page_size = 100

                while True:
                    response = client.search_jobs(
                        page=page,
                        limit=page_size,
                        categories=[category],
                        sort_by_date=True,
                    )

                    if not response.results:
                        break

                    for job in response.results:
                        if job.uuid in seen_uuids:
                            continue
                        seen_uuids.add(job.uuid)

                        jobs_buffer.append(job.model_dump(by_alias=True, mode="json"))
                        fetched_count += 1
                        cat_fetched += 1

                        if on_progress:
                            elapsed = time.monotonic() - start_time
                            on_progress(
                                CrawlProgress(
                                    total_jobs=estimated_total,
                                    fetched=fetched_count,
                                    elapsed=elapsed,
                                    current_category=category,
                                    category_index=cat_idx,
                                    total_categories=total_categories,
                                    category_fetched=cat_fetched,
                                    category_total=cat_total,
                                )
                            )

                    if (page + 1) * page_size >= response.total:
                        break
                    if (page + 1) * page_size >= 10000:
                        break

                    page += 1

                cat_result.fetched_count = cat_fetched
                category_results.append(cat_result)

            client.close()

            return CrawlResult(
                jobs=pd.DataFrame(jobs_buffer),
                fetched_count=fetched_count,
                duration_seconds=time.monotonic() - start_time,
                category_results=category_results,
            )

        except KeyboardInterrupt:
            return CrawlResult(
                jobs=pd.DataFrame(jobs_buffer),
                fetched_count=fetched_count,
                duration_seconds=time.monotonic() - start_time,
                category_results=category_results,
                interrupted=True,
            )
