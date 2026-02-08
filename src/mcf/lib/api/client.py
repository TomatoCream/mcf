"""MyCareersFuture API client."""

from __future__ import annotations

import time

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from mcf.lib.models.company import CompanySearchResponse
from mcf.lib.models.job_detail import JobDetail
from mcf.lib.models.models import SearchResponse

BASE_URL = "https://api.mycareersfuture.gov.sg"
SEARCH_URL = f"{BASE_URL}/v2/search"
JOBS_URL = f"{BASE_URL}/v2/jobs"
COMPANIES_URL = f"{BASE_URL}/v2/companies"

DEFAULT_RATE_LIMIT = 5.0

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


class MCFAPIError(Exception):
    """API returned an error response."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"API Error {status_code}: {message}")


class MCFClient:
    """Client for the MyCareersFuture Singapore API."""

    def __init__(
        self,
        timeout: float = 30.0,
        rate_limit: float | None = DEFAULT_RATE_LIMIT,
    ) -> None:
        self._client = httpx.Client(headers=DEFAULT_HEADERS, timeout=timeout)
        self._rate_limit = rate_limit
        self._last_request_time: float = 0

    def __enter__(self) -> MCFClient:
        return self

    def __exit__(self, *args: object) -> None:
        self._client.close()

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def _wait_for_rate_limit(self) -> None:
        if self._rate_limit is None or self._rate_limit <= 0:
            return
        min_interval = 1.0 / self._rate_limit
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

    def _request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        """Make an HTTP request with retry logic for 403 errors."""
        max_attempts = 5
        attempt = 0
        
        while attempt < max_attempts:
            self._wait_for_rate_limit()
            self._last_request_time = time.monotonic()
            response = self._client.request(method, url, **kwargs)
            
            if response.status_code < 400:
                return response
            
            # For 403 errors, wait longer before retrying (rate limit/IP block)
            if response.status_code == 403:
                attempt += 1
                if attempt >= max_attempts:
                    raise MCFAPIError(response.status_code, response.text)
                # Wait progressively longer: 5 min, 10 min, 15 min, 20 min
                wait_time = 5 * 60 * attempt  # Convert to seconds
                time.sleep(wait_time)
                continue
            
            # For other 4xx/5xx errors, use standard retry with exponential backoff
            if attempt < 2:  # Retry up to 2 more times for non-403 errors
                attempt += 1
                wait_time = min(2 ** attempt, 10)  # Exponential backoff, max 10 seconds
                time.sleep(wait_time)
                continue
            
            # If we've exhausted retries, raise the error
            raise MCFAPIError(response.status_code, response.text)
        
        # Should never reach here, but just in case
        raise MCFAPIError(response.status_code, response.text)

    def search_jobs(
        self,
        keywords: str | None = None,
        *,
        page: int = 0,
        limit: int = 100,
        categories: list[str] | None = None,
        sort_by_date: bool = True,
    ) -> SearchResponse:
        """Search for job postings."""
        params: dict[str, str | int] = {"limit": min(limit, 100), "page": page}
        body: dict[str, object] = {"sessionId": "", "postingCompany": []}

        if keywords:
            body["search"] = keywords
        if categories:
            body["categories"] = categories
        if sort_by_date:
            body["sortBy"] = ["new_posting_date"]

        response = self._request("POST", SEARCH_URL, params=params, json=body)
        return SearchResponse.model_validate(response.json())

    def get_job_detail(self, uuid: str) -> JobDetail:
        """Get job details by UUID."""
        url = f"{JOBS_URL}/{uuid}"
        params = {"updateApplicationCount": "true"}
        response = self._request("GET", url, params=params)
        return JobDetail.model_validate(response.json())

    def search_companies(
        self,
        name: str = "",
        *,
        page: int = 1,
        limit: int = 100,
        order_by: str = "uen",
        order_direction: str = "asc",
        responsive_employer: bool = False,
    ) -> CompanySearchResponse:
        """Search for companies."""
        params: dict[str, str | int | bool] = {
            "name": name,
            "limit": min(limit, 100),
            "page": page,
            "orderBy": order_by,
            "orderDirection": order_direction,
            "responsiveEmployer": str(responsive_employer).lower(),
        }
        response = self._request("GET", COMPANIES_URL, params=params)
        return CompanySearchResponse.model_validate(response.json())
