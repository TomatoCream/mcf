#!/usr/bin/env python3
"""Query helper script for Neon database."""

from __future__ import annotations

import os
import sys
from typing import Any

from mcf.lib.storage.postgres_store import PostgresStore


def get_stats(store: PostgresStore) -> dict[str, Any]:
    """Get database statistics."""
    active_count = store.get_active_job_count()
    recent_runs = store.get_recent_runs(limit=5)
    return {
        "active_jobs": active_count,
        "recent_runs": recent_runs,
    }


def list_jobs(store: PostgresStore, limit: int = 10, keywords: str | None = None) -> list[dict]:
    """List jobs with optional keyword search."""
    return store.search_jobs(limit=limit, keywords=keywords)


def get_crawl_runs(store: PostgresStore, limit: int = 10) -> list[dict]:
    """Get recent crawl runs."""
    return store.get_recent_runs(limit=limit)


def search_jobs(store: PostgresStore, keywords: str, limit: int = 20) -> list[dict]:
    """Search jobs by keywords."""
    return store.search_jobs(limit=limit, keywords=keywords)


def get_job(store: PostgresStore, job_uuid: str) -> dict | None:
    """Get job details by UUID."""
    return store.get_job(job_uuid)


def main() -> None:
    """Main entry point for CLI usage."""
    import argparse

    parser = argparse.ArgumentParser(description="Query MCF database")
    parser.add_argument(
        "--db-url",
        default=os.getenv("DATABASE_URL"),
        help="PostgreSQL connection URL (or set DATABASE_URL env var)",
    )
    parser.add_argument("--stats", action="store_true", help="Show database statistics")
    parser.add_argument("--list", action="store_true", help="List jobs")
    parser.add_argument("--search", type=str, help="Search jobs by keywords")
    parser.add_argument("--runs", action="store_true", help="Show recent crawl runs")
    parser.add_argument("--job", type=str, help="Get job by UUID")
    parser.add_argument("--limit", type=int, default=10, help="Limit results (default: 10)")

    args = parser.parse_args()

    if not args.db_url:
        print("Error: DATABASE_URL not set. Use --db-url or set DATABASE_URL environment variable.")
        sys.exit(1)

    store = PostgresStore(args.db_url)
    try:
        if args.stats:
            stats = get_stats(store)
            print(f"\n📊 Database Statistics")
            print(f"Active Jobs: {stats['active_jobs']:,}")
            print(f"\nRecent Crawl Runs:")
            for run in stats["recent_runs"]:
                print(f"  Run ID: {run['run_id']}")
                print(f"    Finished: {run.get('finished_at', 'N/A')}")
                print(f"    Total Seen: {run['total_seen']:,}")
                print(f"    Added: {run['added']:,} | Maintained: {run['maintained']:,} | Removed: {run['removed']:,}")
                print()

        elif args.runs:
            runs = get_crawl_runs(store, limit=args.limit)
            print(f"\n📋 Recent Crawl Runs (last {len(runs)}):")
            for run in runs:
                print(f"  {run['run_id']}")
                print(f"    Finished: {run.get('finished_at', 'N/A')}")
                print(f"    Stats: {run['total_seen']:,} seen | +{run['added']:,} | ~{run['maintained']:,} | -{run['removed']:,}")
                print()

        elif args.search:
            jobs = search_jobs(store, args.search, limit=args.limit)
            print(f"\n🔍 Search Results for '{args.search}' ({len(jobs)} jobs):")
            for job in jobs:
                print(f"  {job['title']}")
                print(f"    Company: {job.get('company_name', 'N/A')}")
                print(f"    Location: {job.get('location', 'N/A')}")
                print(f"    UUID: {job['job_uuid']}")
                print()

        elif args.job:
            job = get_job(store, args.job)
            if job:
                print(f"\n📄 Job Details:")
                print(f"  UUID: {job['job_uuid']}")
                print(f"  Title: {job.get('title', 'N/A')}")
                print(f"  Company: {job.get('company_name', 'N/A')}")
                print(f"  Location: {job.get('location', 'N/A')}")
                print(f"  Active: {job.get('is_active', False)}")
                if job.get('description'):
                    desc = job['description'][:200] + "..." if len(job['description']) > 200 else job['description']
                    print(f"  Description: {desc}")
            else:
                print(f"Job not found: {args.job}")

        elif args.list:
            jobs = list_jobs(store, limit=args.limit)
            print(f"\n📋 Jobs (showing {len(jobs)}):")
            for job in jobs:
                print(f"  {job['title']}")
                print(f"    Company: {job.get('company_name', 'N/A')}")
                print(f"    Location: {job.get('location', 'N/A')}")
                print(f"    UUID: {job['job_uuid']}")
                print()

        else:
            # Default: show stats
            stats = get_stats(store)
            print(f"\n📊 Database Statistics")
            print(f"Active Jobs: {stats['active_jobs']:,}")
            if stats["recent_runs"]:
                latest = stats["recent_runs"][0]
                print(f"\nLatest Crawl Run:")
                print(f"  Run ID: {latest['run_id']}")
                print(f"  Finished: {latest.get('finished_at', 'N/A')}")
                print(f"  Added: {latest['added']:,} | Maintained: {latest['maintained']:,} | Removed: {latest['removed']:,}")
            print("\nUse --help for more options")

    finally:
        store.close()


if __name__ == "__main__":
    main()
