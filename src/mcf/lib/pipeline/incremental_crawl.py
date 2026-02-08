"""Incremental crawl pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from mcf.lib.api.client import MCFClient
from mcf.lib.crawler.crawler import Crawler
from mcf.lib.embeddings.embedder import Embedder, EmbedderConfig
from mcf.lib.storage.base import RunStats, Storage


@dataclass(frozen=True)
class IncrementalCrawlResult:
    run: RunStats
    total_seen: int
    added: list[str]
    maintained: list[str]
    removed: list[str]


def _extract_best_effort_fields(job_detail_json: dict) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    # The API model can evolve; keep extraction defensive.
    title = job_detail_json.get("title") or job_detail_json.get("jobTitle")
    description = job_detail_json.get("description") or job_detail_json.get("jobDescription")

    company_name = None
    company = job_detail_json.get("company") or job_detail_json.get("postingCompany")
    if isinstance(company, dict):
        company_name = company.get("name") or company.get("companyName")

    location = None
    addr = job_detail_json.get("address") or job_detail_json.get("workLocation")
    if isinstance(addr, dict):
        # pick something readable
        location = addr.get("country") or addr.get("postalCode") or addr.get("streetAddress")

    # Extract job URL from metadata
    job_url = None
    metadata = job_detail_json.get("metadata")
    if isinstance(metadata, dict):
        job_url = metadata.get("jobDetailsUrl")
    # Also check top-level
    if not job_url:
        job_url = job_detail_json.get("jobDetailsUrl")

    return title, company_name, location, description, job_url


def run_incremental_crawl(
    *,
    store: Storage,
    rate_limit: float = 4.0,
    categories: Sequence[str] | None = None,
    limit: int | None = None,
    on_progress=None,
) -> IncrementalCrawlResult:
    """Run an incremental crawl.

    - Lists UUIDs (cheap)
    - Diffs against DB to compute added/maintained/removed
    - Fetches job detail only for newly added UUIDs
    """
    try:
        run = store.begin_run(kind="incremental", categories=list(categories) if categories else None)

        crawler = Crawler(rate_limit=rate_limit)
        seen = crawler.list_job_uuids_all_categories(
            categories=list(categories) if categories else None,
            limit=limit,
            on_progress=on_progress,
        )
        seen_set = set(seen)
        existing = store.existing_job_uuids()
        active = store.active_job_uuids()

        added = sorted(seen_set - existing)
        maintained = sorted(seen_set & existing)
        # Only a *full crawl* can reliably infer removals.
        # If user filters by categories or uses a limit, we must not deactivate
        # the rest of the universe (they simply weren't checked).
        is_full_universe = (categories is None) and (limit is None)
        removed = sorted(active - seen_set) if is_full_universe else []

        # Update statuses in DB first, then fetch details for added.
        store.record_statuses(run.run_id, added=added, maintained=maintained, removed=removed)
        store.touch_jobs(run_id=run.run_id, job_uuids=maintained)
        if removed:
            store.deactivate_jobs(run_id=run.run_id, job_uuids=removed)

        if added:
            # Initialize embedder for generating embeddings
            embedder = Embedder(EmbedderConfig())
            
            with MCFClient(rate_limit=rate_limit) as client:
                for uuid in added:
                    detail = client.get_job_detail(uuid)
                    raw = detail.model_dump(by_alias=True, mode="json")
                    title, company_name, location, description, job_url = _extract_best_effort_fields(raw)
                    
                    # Generate embedding from description (if available)
                    embedding = None
                    if description:
                        try:
                            embedding = embedder.embed_text(description)
                        except Exception as e:
                            # Log error but continue - embedding generation is optional
                            print(f"Warning: Failed to generate embedding for job {uuid}: {e}")
                    
                    # Store job details (without description text)
                    store.upsert_new_job_detail(
                        run_id=run.run_id,
                        job_uuid=uuid,
                        title=title,
                        company_name=company_name,
                        location=location,
                        job_url=job_url,
                        raw_json=None,  # Don't store raw_json to save space
                    )
                    
                    # Store embedding if generated
                    if embedding:
                        store.upsert_embedding(
                            job_uuid=uuid,
                            model_name=embedder.model_name,
                            embedding=embedding,
                        )

        store.finish_run(
            run.run_id,
            total_seen=len(seen_set),
            added=len(added),
            maintained=len(maintained),
            removed=len(removed),
        )

        final_run = RunStats(
            run_id=run.run_id,
            started_at=run.started_at,
            finished_at=None,
            total_seen=len(seen_set),
            added=len(added),
            maintained=len(maintained),
            removed=len(removed),
        )
        return IncrementalCrawlResult(
            run=final_run,
            total_seen=len(seen_set),
            added=added,
            maintained=maintained,
            removed=removed,
        )
    finally:
        pass  # Store cleanup handled by caller

