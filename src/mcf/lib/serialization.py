"""Job serialization utilities for parquet and JSON storage."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcf.lib.models.models import JobPosting


def flatten_job(
    job: JobPosting,
    crawl_date: date,
    crawl_timestamp: datetime,
) -> dict[str, Any]:
    """Flatten a JobPosting to a dict for parquet storage.

    Schema designed for historical analysis:
    - crawl_date: Partition key (YYYY-MM-DD)
    - job_uuid: Primary key for joining across time
    - last_seen_timestamp: Exact crawl time for partial day handling

    Args:
        job: The JobPosting to flatten.
        crawl_date: The partition date.
        crawl_timestamp: Exact timestamp of the crawl.

    Returns:
        Flattened dictionary suitable for DataFrame/parquet storage.
    """
    # Extract nested values safely
    salary_min = job.salary.minimum if job.salary else None
    salary_max = job.salary.maximum if job.salary else None
    salary_type = (
        job.salary.type.salary_type.value
        if job.salary and job.salary.type
        else None
    )

    # Address/location fields
    region = None
    district_location = None
    is_overseas = False
    if job.address:
        is_overseas = job.address.is_overseas
        if job.address.districts:
            region = job.address.districts[0].region
            district_location = job.address.districts[0].location

    # Employment types as comma-separated
    employment_types = (
        ",".join(et.employment_type for et in job.employment_types)
        if job.employment_types
        else None
    )

    # Position levels as comma-separated
    position_levels = (
        ",".join(pl.position for pl in job.position_levels)
        if job.position_levels
        else None
    )

    # Categories as comma-separated
    categories = (
        ",".join(c.category for c in job.categories)
        if job.categories
        else None
    )

    # Skills as comma-separated
    skills = (
        ",".join(s.skill for s in job.skills)
        if job.skills
        else None
    )

    # Schemes as comma-separated (extract scheme names)
    schemes = (
        ",".join(s.name for s in job.schemes if s.name)
        if job.schemes
        else None
    )

    # Flexible work arrangements
    flex_arrangements = (
        ",".join(f.arrangement for f in job.flexible_work_arrangements if f.arrangement)
        if job.flexible_work_arrangements
        else None
    )

    return {
        # Partition & Identity
        "crawl_date": crawl_date,
        "job_uuid": job.uuid,
        "last_seen_timestamp": crawl_timestamp,
        # Core job info
        "title": job.title,
        "job_post_id": job.metadata.job_post_id,
        "job_details_url": job.metadata.job_details_url,
        "posting_date": job.metadata.new_posting_date,
        "updated_at": job.metadata.updated_at,
        # Company
        "company_name": job.company_name,
        "posted_company_name": job.posted_company.name,
        "posted_company_uen": job.posted_company.uen,
        "hiring_company_name": job.hiring_company.name if job.hiring_company else None,
        "hiring_company_uen": job.hiring_company.uen if job.hiring_company else None,
        "is_hide_hiring_employer": job.metadata.is_hide_hiring_employer_name,
        "is_posted_on_behalf": job.metadata.is_posted_on_behalf,
        # Salary
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_type": salary_type,
        "is_hide_salary": job.metadata.is_hide_salary,
        # Location
        "region": region,
        "district_location": district_location,
        "is_overseas": is_overseas,
        "overseas_country": job.address.overseas_country if job.address else None,
        "postal_code": job.address.postal_code if job.address else None,
        # Classifications
        "employment_types": employment_types,
        "position_levels": position_levels,
        "categories": categories,
        "skills": skills,
        "schemes": schemes,
        "flex_arrangements": flex_arrangements,
        "shift_pattern": job.shift_pattern,
        # Status & metrics
        "job_status": job.status.job_status.value if job.status else None,
        "total_applications": job.metadata.total_number_job_application,
        # Scoring (useful for understanding API ranking)
        "score": job.score,
    }

