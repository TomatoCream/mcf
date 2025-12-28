"""MyCareersFuture API client."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from mcf.lib.models.models import (
    CommonMetadata,
    JobPosting,
    JobSearchResponse,
    ProfileResponse,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass
class JobPosition:
    """Position info for a job in iteration."""

    job_index: int
    """Current job index (1-indexed)."""

    total_jobs: int
    """Total jobs available."""

    page: int
    """Current page (0-indexed)."""

    total_pages: int
    """Total pages available."""

    page_index: int
    """Index within current page (1-indexed)."""

    page_size: int
    """Jobs in current page."""

# API endpoints
BASE_URL = "https://api.mycareersfuture.gov.sg"
SEARCH_URL = f"{BASE_URL}/v2/search"
PROFILE_URL = f"{BASE_URL}/profile"

# Default rate limit (requests per second)
DEFAULT_RATE_LIMIT = 5.0

# Default headers required by the API
DEFAULT_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-GB,en;q=0.9",
    "content-type": "application/json",
    "mcf-client": "jobseeker",
    "origin": "https://www.mycareersfuture.gov.sg",
    "referer": "https://www.mycareersfuture.gov.sg/",
    "user-agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
    ),
}

# GraphQL query for metadata
METADATA_QUERY = """
query getAllEntities {
  common {
    employmentTypes {
      id
      name
    }
    ssocList {
      ssoc
      ssocTitle
    }
    ssicList {
      code
      description
    }
    countriesList {
      codeNumber
      description
      code
    }
    employmentStatusList {
      id
      description
    }
    ssecEqaList {
      code
      description
    }
    ssecFosList {
      code
      description
    }
  }
}
"""


class MCFClientError(Exception):
    """Base exception for MCF client errors."""

    pass


class MCFAPIError(MCFClientError):
    """API returned an error response."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"API Error {status_code}: {message}")


class MCFClient:
    """Client for the MyCareersFuture Singapore API.

    Provides methods to search for jobs and retrieve metadata.

    Example:
        >>> client = MCFClient()
        >>> results = client.search_jobs(keywords="python developer")
        >>> for job in results.results:
        ...     print(job.title, job.salary.display)
    """

    def __init__(
        self,
        timeout: float = 30.0,
        rate_limit: float | None = DEFAULT_RATE_LIMIT,
    ) -> None:
        """Initialize the MCF client.

        Args:
            timeout: Request timeout in seconds.
            rate_limit: Max requests per second (None to disable).
        """
        self._client = httpx.Client(
            headers=DEFAULT_HEADERS,
            timeout=timeout,
        )
        self._rate_limit = rate_limit
        self._last_request_time: float = 0
        self._request_count: int = 0

    def __enter__(self) -> MCFClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    @property
    def request_count(self) -> int:
        """Number of requests made by this client."""
        return self._request_count

    def _wait_for_rate_limit(self) -> None:
        """Wait if necessary to respect rate limit."""
        if self._rate_limit is None or self._rate_limit <= 0:
            return

        min_interval = 1.0 / self._rate_limit
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _request(
        self,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        """Make an HTTP request with retry logic and rate limiting."""
        self._wait_for_rate_limit()
        self._last_request_time = time.monotonic()
        self._request_count += 1

        response = self._client.request(method, url, **kwargs)
        if response.status_code >= 400:
            raise MCFAPIError(response.status_code, response.text)
        return response

    def search_jobs(
        self,
        keywords: str | None = None,
        *,
        page: int = 0,
        limit: int = 100,
        categories: list[str] | None = None,
        sort_by_date: bool = False,
    ) -> JobSearchResponse:
        """Search for job postings.

        Args:
            keywords: Search keywords (job title, skills, etc.).
            page: Page number (0-indexed).
            limit: Number of results per page (max 100).
            categories: Filter by category names (e.g., ["Information Technology"]).
            sort_by_date: Sort by posting date (newest first).

        Returns:
            JobSearchResponse containing matching job postings.

        Raises:
            MCFAPIError: If the API returns an error.
        """
        params: dict[str, str | int] = {
            "limit": min(limit, 100),
            "page": page,
        }

        body: dict[str, object] = {
            "sessionId": "",
            "postingCompany": [],
        }

        if keywords:
            body["search"] = keywords

        if categories:
            body["categories"] = categories

        if sort_by_date:
            body["sortBy"] = ["new_posting_date"]

        response = self._request(
            "POST",
            SEARCH_URL,
            params=params,
            json=body,
        )
        return JobSearchResponse.model_validate(response.json())

    def iter_jobs(
        self,
        keywords: str | None = None,
        *,
        limit: int = 100,
        max_jobs: int | None = None,
        categories: list[str] | None = None,
        sort_by_date: bool = False,
    ) -> Iterator[tuple[JobPosting, JobPosition]]:
        """Iterate through individual job postings with position info.

        Args:
            keywords: Search keywords.
            limit: Results per page.
            max_jobs: Maximum total jobs to fetch (None for all).
            categories: Filter by category names.
            sort_by_date: Sort by posting date (newest first).

        Yields:
            Tuple of (JobPosting, JobPosition) for each job.

        Example:
            >>> for job, pos in client.iter_jobs("python", max_jobs=50):
            ...     print(f"[{pos.job_index}/{pos.total_jobs}] {job.title}")
        """
        page = 0
        job_index = 0

        while True:
            response = self.search_jobs(
                keywords=keywords,
                page=page,
                limit=limit,
                categories=categories,
                sort_by_date=sort_by_date,
            )
            total_pages = (response.total + limit - 1) // limit

            for i, job in enumerate(response.results, 1):
                job_index += 1

                pos = JobPosition(
                    job_index=job_index,
                    total_jobs=response.total,
                    page=page,
                    total_pages=total_pages,
                    page_index=i,
                    page_size=len(response.results),
                )
                yield job, pos

                if max_jobs is not None and job_index >= max_jobs:
                    return

            if not response.results or (page + 1) * limit >= response.total:
                break
            page += 1

    def get_metadata(self) -> CommonMetadata:
        """Fetch common metadata (employment types, classifications, etc.).

        Returns:
            CommonMetadata containing reference data.

        Raises:
            MCFAPIError: If the API returns an error.
        """
        body = {
            "operationName": "getAllEntities",
            "variables": {},
            "query": METADATA_QUERY,
        }
        response = self._request("POST", PROFILE_URL, json=body)
        profile = ProfileResponse.model_validate(response.json())
        return profile.data.common

