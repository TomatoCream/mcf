"""MyCareersFuture API client."""

from mcf.lib.api.client import MCFAPIError, MCFClient
from mcf.lib.categories import CATEGORIES
from mcf.lib.models.models import Job, SearchResponse

__version__ = "0.1.0"
__all__ = [
    "MCFClient",
    "MCFAPIError",
    "Job",
    "SearchResponse",
    "CATEGORIES",
]
