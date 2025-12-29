"""MyCareersFuture API client."""

from __future__ import annotations

import time

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from mcf.lib.models.models import SearchResponse

BASE_URL = "https://api.mycareersfuture.gov.sg"
SEARCH_URL = f"{BASE_URL}/v2/search"

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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        self._wait_for_rate_limit()
        self._last_request_time = time.monotonic()
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
