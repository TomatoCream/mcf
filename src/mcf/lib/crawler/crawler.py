"""Crawler for archiving job postings to parquet and JSON."""

from __future__ import annotations

import gzip
import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import pandas as pd

from mcf.lib.api.client import MCFClient
from mcf.lib.categories import CATEGORIES

if TYPE_CHECKING:
    from mcf.lib.models.models import Job


def flatten_job(job: Job, crawl_date: date, crawl_timestamp: datetime) -> dict:
    """Flatten a Job model into a dict suitable for parquet storage.

    Args:
        job: The Job model to flatten.
        crawl_date: Date of the crawl.
        crawl_timestamp: Timestamp when crawl started.

    Returns:
        Flat dictionary with scalar values.
    """
    result: dict = {
        "crawl_date": crawl_date.isoformat(),
        "crawl_timestamp": crawl_timestamp.isoformat(),
        "uuid": job.uuid,
        "title": job.title,
        "score": job.score,
    }

    # Company info
    if job.hiringCompany:
        result["hiring_company_name"] = job.hiringCompany.name
        result["hiring_company_uen"] = job.hiringCompany.uen
    if job.postedCompany:
        result["posted_company_name"] = job.postedCompany.name
        result["posted_company_uen"] = job.postedCompany.uen

    # Salary
    if job.salary:
        result["salary_min"] = job.salary.minimum
        result["salary_max"] = job.salary.maximum
        if job.salary.type:
            result["salary_type"] = job.salary.type.salaryType

    # Metadata
    if job.metadata:
        result["job_post_id"] = job.metadata.jobPostId
        result["new_posting_date"] = job.metadata.newPostingDate
        result["updated_at"] = job.metadata.updatedAt
        result["job_details_url"] = job.metadata.jobDetailsUrl
        result["total_applications"] = job.metadata.totalNumberJobApplication

    # Categories (as comma-separated string)
    if job.categories:
        result["categories"] = ",".join(c.category for c in job.categories)

    # Employment types
    if job.employmentTypes:
        result["employment_types"] = ",".join(e.employmentType for e in job.employmentTypes)

    # Skills
    if job.skills:
        result["skills"] = ",".join(s.skill for s in job.skills)

    # Address
    if job.address:
        if job.address.districts:
            result["location"] = job.address.districts[0].location
            result["region"] = job.address.districts[0].region
        result["postal_code"] = job.address.postalCode

    return result


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

    fetched_count: int = 0
    """Total jobs fetched from API."""

    saved_count: int = 0
    """Total jobs saved to disk."""

    part_count: int = 0
    """Number of part files written."""

    duration_seconds: float = 0
    """Total crawl duration."""

    partition_dir: Path | None = None
    """Directory where files were saved."""

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

    saved: int
    """Jobs saved to disk so far."""

    part_num: int
    """Current part file number."""

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


ProgressCallback = Callable[[CrawlProgress], None]


@dataclass
class Crawler:
    """Crawler for archiving all job postings.

    Fetches all jobs from MyCareersFuture and saves to partitioned storage.
    Supports both parquet (for analysis) and JSON (for debugging/full data).

    Example:
        >>> crawler = Crawler(output_dir=Path("data/jobs"))
        >>> result = crawler.crawl(categories=["Information Technology"])
        >>> print(f"Saved {result.saved_count} jobs")
    """

    output_dir: Path = field(default_factory=lambda: Path("data/jobs"))
    """Base output directory for saved files."""

    batch_size: int = 1000
    """Jobs per batch before flushing to disk."""

    rate_limit: float = 5.0
    """API requests per second."""

    save_json: bool = True
    """Whether to save raw JSON alongside parquet."""

    dry_run: bool = False
    """If True, fetch but don't save."""

    def crawl(
        self,
        *,
        categories: list[str] | None = None,
        target_date: date | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> CrawlResult:
        """Crawl all jobs matching the criteria.

        Args:
            categories: Filter by category names (e.g., ["Information Technology"]).
            target_date: Override crawl date (default: today).
            on_progress: Callback for progress updates.

        Returns:
            CrawlResult with statistics about the crawl.
        """
        if target_date is None:
            target_date = date.today()

        crawl_timestamp = datetime.now()

        # Create partition directory
        partition_dir = self.output_dir / f"crawl_date={target_date.isoformat()}"
        if not self.dry_run:
            partition_dir.mkdir(parents=True, exist_ok=True)

        # Initialize state
        fetched_count = 0
        saved_count = 0
        part_num = 0
        batch_buffer: list[dict] = []
        raw_json_buffer: list[dict] = []
        start_time = time.monotonic()

        result = CrawlResult(partition_dir=partition_dir)

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
                # Fetch page
                response = client.search_jobs(
                    page=page,
                    limit=page_size,
                    categories=categories,
                    sort_by_date=True,
                )

                if not response.results:
                    break

                # Process jobs in this page
                for job in response.results:
                    flat_job = flatten_job(job, target_date, crawl_timestamp)
                    batch_buffer.append(flat_job)

                    if self.save_json:
                        raw_json_buffer.append(job.model_dump(by_alias=True, mode="json"))

                    fetched_count += 1

                    # Flush batch to disk when buffer is full
                    if len(batch_buffer) >= self.batch_size:
                        if not self.dry_run:
                            part_num += 1
                            self._write_batch(
                                partition_dir,
                                part_num,
                                batch_buffer,
                                raw_json_buffer,
                            )

                        saved_count += len(batch_buffer)
                        batch_buffer.clear()
                        raw_json_buffer.clear()

                    # Progress callback
                    if on_progress:
                        elapsed = time.monotonic() - start_time
                        on_progress(
                            CrawlProgress(
                                total_jobs=total_jobs,
                                fetched=fetched_count,
                                saved=saved_count,
                                part_num=part_num,
                                elapsed=elapsed,
                            )
                        )

                # Check if we've fetched all jobs
                if (page + 1) * page_size >= response.total:
                    break

                page += 1

            # Flush remaining buffer
            if batch_buffer:
                if not self.dry_run:
                    part_num += 1
                    self._write_batch(
                        partition_dir,
                        part_num,
                        batch_buffer,
                        raw_json_buffer,
                    )
                saved_count += len(batch_buffer)

            client.close()

            result.fetched_count = fetched_count
            result.saved_count = saved_count
            result.part_count = part_num
            result.duration_seconds = time.monotonic() - start_time

        except KeyboardInterrupt:
            # Graceful shutdown - save whatever we have
            if batch_buffer and not self.dry_run:
                part_num += 1
                self._write_batch(
                    partition_dir,
                    part_num,
                    batch_buffer,
                    raw_json_buffer,
                )
                saved_count += len(batch_buffer)

            result.fetched_count = fetched_count
            result.saved_count = saved_count
            result.part_count = part_num
            result.duration_seconds = time.monotonic() - start_time
            result.interrupted = True
            raise

        return result

    def crawl_all_categories(
        self,
        *,
        target_date: date | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> CrawlResult:
        """Crawl all categories to get around the 10k pagination limit.

        The API limits pagination to ~10k results. By crawling each category
        separately, we can get all jobs even when total exceeds 10k.

        Args:
            target_date: Override crawl date (default: today).
            on_progress: Callback for progress updates.

        Returns:
            CrawlResult with combined statistics from all categories.
        """
        if target_date is None:
            target_date = date.today()

        crawl_timestamp = datetime.now()

        # Create partition directory
        partition_dir = self.output_dir / f"crawl_date={target_date.isoformat()}"
        if not self.dry_run:
            partition_dir.mkdir(parents=True, exist_ok=True)

        # Initialize state
        fetched_count = 0
        saved_count = 0
        part_num = 0
        seen_uuids: set[str] = set()  # Deduplicate jobs across categories
        category_results: list[CategoryResult] = []
        start_time = time.monotonic()

        result = CrawlResult(partition_dir=partition_dir)

        try:
            client = MCFClient(rate_limit=self.rate_limit)

            # First, count jobs per category to estimate total
            category_counts: list[tuple[str, int]] = []
            for cat in CATEGORIES:
                response = client.search_jobs(limit=1, categories=[cat])
                category_counts.append((cat, response.total))

            # Estimate total (may have duplicates across categories)
            estimated_total = sum(count for _, count in category_counts)
            total_categories = len(CATEGORIES)

            # Crawl each category
            for cat_idx, (category, cat_total) in enumerate(category_counts, 1):
                cat_result = CategoryResult(
                    category=category,
                    total_available=cat_total,
                )

                if cat_total == 0:
                    cat_result.skipped = True
                    category_results.append(cat_result)
                    continue

                batch_buffer: list[dict] = []
                raw_json_buffer: list[dict] = []
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
                        # Deduplicate: jobs can appear in multiple categories
                        if job.uuid in seen_uuids:
                            continue
                        seen_uuids.add(job.uuid)

                        flat_job = flatten_job(job, target_date, crawl_timestamp)
                        batch_buffer.append(flat_job)

                        if self.save_json:
                            raw_json_buffer.append(
                                job.model_dump(by_alias=True, mode="json")
                            )

                        fetched_count += 1
                        cat_fetched += 1

                        # Flush batch
                        if len(batch_buffer) >= self.batch_size:
                            if not self.dry_run:
                                part_num += 1
                                self._write_batch(
                                    partition_dir,
                                    part_num,
                                    batch_buffer,
                                    raw_json_buffer,
                                )
                            saved_count += len(batch_buffer)
                            batch_buffer.clear()
                            raw_json_buffer.clear()

                        # Progress callback
                        if on_progress:
                            elapsed = time.monotonic() - start_time
                            on_progress(
                                CrawlProgress(
                                    total_jobs=estimated_total,
                                    fetched=fetched_count,
                                    saved=saved_count,
                                    part_num=part_num,
                                    elapsed=elapsed,
                                    current_category=category,
                                    category_index=cat_idx,
                                    total_categories=total_categories,
                                    category_fetched=cat_fetched,
                                    category_total=cat_total,
                                )
                            )

                    # Check pagination limit
                    if (page + 1) * page_size >= response.total:
                        break
                    if (page + 1) * page_size >= 10000:
                        # Hit API limit, move to next category
                        break

                    page += 1

                # Flush remaining for this category
                if batch_buffer:
                    if not self.dry_run:
                        part_num += 1
                        self._write_batch(
                            partition_dir,
                            part_num,
                            batch_buffer,
                            raw_json_buffer,
                        )
                    saved_count += len(batch_buffer)
                    batch_buffer.clear()
                    raw_json_buffer.clear()

                cat_result.fetched_count = cat_fetched
                category_results.append(cat_result)

            client.close()

            result.fetched_count = fetched_count
            result.saved_count = saved_count
            result.part_count = part_num
            result.duration_seconds = time.monotonic() - start_time
            result.category_results = category_results

        except KeyboardInterrupt:
            result.fetched_count = fetched_count
            result.saved_count = saved_count
            result.part_count = part_num
            result.duration_seconds = time.monotonic() - start_time
            result.category_results = category_results
            result.interrupted = True
            raise

        return result

    def _write_batch(
        self,
        partition_dir: Path,
        part_num: int,
        flat_jobs: list[dict],
        raw_jobs: list[dict],
    ) -> None:
        """Write a batch of jobs to disk.

        Args:
            partition_dir: Directory to write to.
            part_num: Part number for filename.
            flat_jobs: Flattened jobs for parquet.
            raw_jobs: Raw job dicts for JSON.
        """
        part_name = f"part-{part_num:04d}"

        # Write parquet
        parquet_path = partition_dir / f"{part_name}.parquet"
        df = pd.DataFrame(flat_jobs)
        df.to_parquet(parquet_path, index=False)

        # Write JSON (gzipped for space efficiency)
        if self.save_json and raw_jobs:
            json_path = partition_dir / f"{part_name}.json.gz"
            with gzip.open(json_path, "wt", encoding="utf-8") as f:
                json.dump(raw_jobs, f, ensure_ascii=False, default=str)

