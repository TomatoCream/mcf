"""MyCareersFuture API client."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from mcf.lib.models.models import (
    CommonMetadata,
    JobSearchResponse,
    ProfileResponse,
    SearchFilters,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

# API endpoints
BASE_URL = "https://api.mycareersfuture.gov.sg"
SEARCH_URL = f"{BASE_URL}/v2/search"
PROFILE_URL = f"{BASE_URL}/profile"

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

    def __init__(self, timeout: float = 30.0) -> None:
        """Initialize the MCF client.

        Args:
            timeout: Request timeout in seconds.
        """
        self._client = httpx.Client(
            headers=DEFAULT_HEADERS,
            timeout=timeout,
        )

    def __enter__(self) -> MCFClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

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
        """Make an HTTP request with retry logic."""
        response = self._client.request(method, url, **kwargs)
        if response.status_code >= 400:
            raise MCFAPIError(response.status_code, response.text)
        return response

    def search_jobs(
        self,
        keywords: str | None = None,
        *,
        salary_min: int | None = None,
        salary_max: int | None = None,
        employment_types: list[str] | None = None,
        categories: list[str] | None = None,
        page: int = 0,
        limit: int = 20,
    ) -> JobSearchResponse:
        """Search for job postings.

        Args:
            keywords: Search keywords (job title, skills, etc.).
            salary_min: Minimum salary filter.
            salary_max: Maximum salary filter.
            employment_types: Filter by employment types (e.g., ["Full Time"]).
            categories: Filter by job categories.
            page: Page number (0-indexed).
            limit: Number of results per page (max 100).

        Returns:
            JobSearchResponse containing matching job postings.

        Raises:
            MCFAPIError: If the API returns an error.
        """
        # Build query parameters
        params: dict[str, str | int] = {
            "limit": min(limit, 100),
            "page": page,
        }

        # Build request body
        body: dict[str, object] = {
            "sessionId": "",
            "postingCompany": [],
        }

        if keywords:
            body["search"] = keywords

        if salary_min is not None:
            body["salary"] = body.get("salary", {})
            body["salary"]["minimum"] = salary_min  # type: ignore[index]

        if salary_max is not None:
            body["salary"] = body.get("salary", {})
            body["salary"]["maximum"] = salary_max  # type: ignore[index]

        if employment_types:
            body["employmentTypes"] = employment_types

        if categories:
            body["categories"] = categories

        response = self._request(
            "POST",
            SEARCH_URL,
            params=params,
            json=body,
        )
        return JobSearchResponse.model_validate(response.json())

    def search_jobs_iter(
        self,
        keywords: str | None = None,
        *,
        salary_min: int | None = None,
        salary_max: int | None = None,
        employment_types: list[str] | None = None,
        categories: list[str] | None = None,
        limit: int = 20,
        max_pages: int | None = None,
    ) -> Iterator[JobSearchResponse]:
        """Iterate through all pages of job search results.

        Args:
            keywords: Search keywords.
            salary_min: Minimum salary filter.
            salary_max: Maximum salary filter.
            employment_types: Filter by employment types.
            categories: Filter by job categories.
            limit: Results per page.
            max_pages: Maximum number of pages to fetch (None for all).

        Yields:
            JobSearchResponse for each page.
        """
        page = 0
        while True:
            if max_pages is not None and page >= max_pages:
                break

            response = self.search_jobs(
                keywords=keywords,
                salary_min=salary_min,
                salary_max=salary_max,
                employment_types=employment_types,
                categories=categories,
                page=page,
                limit=limit,
            )
            yield response

            # Check if there are more pages
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

    def get_filters(self) -> SearchFilters:
        """Get default search filters.

        Returns:
            SearchFilters with default values.
        """
        return SearchFilters()

