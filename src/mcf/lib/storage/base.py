"""Storage abstraction interface for job crawler."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence


@dataclass(frozen=True)
class RunStats:
    """Statistics for a crawl run."""

    run_id: str
    started_at: datetime
    finished_at: datetime | None
    total_seen: int
    added: int
    maintained: int
    removed: int


class Storage(ABC):
    """Abstract storage interface for incremental crawl state."""

    @abstractmethod
    def begin_run(self, *, kind: str, categories: Sequence[str] | None) -> RunStats:
        """Begin a new crawl run."""
        pass

    @abstractmethod
    def finish_run(
        self, run_id: str, *, total_seen: int, added: int, maintained: int, removed: int
    ) -> None:
        """Finish a crawl run with statistics."""
        pass

    @abstractmethod
    def existing_job_uuids(self) -> set[str]:
        """Get set of all existing job UUIDs."""
        pass

    @abstractmethod
    def active_job_uuids(self) -> set[str]:
        """Get set of all active job UUIDs."""
        pass

    @abstractmethod
    def record_statuses(
        self, run_id: str, *, added: Iterable[str], maintained: Iterable[str], removed: Iterable[str]
    ) -> None:
        """Record job statuses for a run."""
        pass

    @abstractmethod
    def touch_jobs(self, *, run_id: str, job_uuids: Iterable[str]) -> None:
        """Update last_seen timestamp for maintained jobs."""
        pass

    @abstractmethod
    def deactivate_jobs(self, *, run_id: str, job_uuids: Iterable[str]) -> None:
        """Deactivate jobs that were removed."""
        pass

    @abstractmethod
    def upsert_new_job_detail(
        self,
        *,
        run_id: str,
        job_uuid: str,
        title: str | None,
        company_name: str | None,
        location: str | None,
        job_url: str | None,
        raw_json: dict | None = None,
    ) -> None:
        """Insert or update a job detail."""
        pass

    @abstractmethod
    def get_job(self, job_uuid: str) -> dict | None:
        """Get job by UUID."""
        pass

    @abstractmethod
    def search_jobs(
        self, *, limit: int = 100, offset: int = 0, category: str | None = None, keywords: str | None = None
    ) -> list[dict]:
        """Search jobs with filters."""
        pass

    @abstractmethod
    def get_recent_runs(self, limit: int = 10) -> list[dict]:
        """Get recent crawl runs with statistics."""
        pass

    @abstractmethod
    def get_active_job_count(self) -> int:
        """Get count of active jobs."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the storage connection."""
        pass
