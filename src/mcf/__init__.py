"""MyCareersFuture API client and CLI.

A Python library and CLI for searching jobs on MyCareersFuture Singapore.

Example:
    >>> from mcf import MCFClient
    >>> client = MCFClient()
    >>> results = client.search_jobs("python developer")
    >>> for job in results.results:
    ...     print(f"{job.title}")
"""

from mcf.lib.api.client import JobPosition, MCFAPIError, MCFClient, MCFClientError
from mcf.lib.models.models import CommonData, Job, SearchResponse

__version__ = "0.1.0"
__all__ = [
    "MCFClient",
    "MCFAPIError",
    "MCFClientError",
    "JobPosition",
    "Job",
    "SearchResponse",
    "CommonData",
]
