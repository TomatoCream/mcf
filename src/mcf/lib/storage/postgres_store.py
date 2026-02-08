"""PostgreSQL-backed storage for incremental crawling."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable, Sequence

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from mcf.lib.storage.base import RunStats, Storage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PostgresStore(Storage):
    """PostgreSQL persistence layer for incremental crawl state."""

    def __init__(self, database_url: str) -> None:
        """Initialize PostgreSQL store with connection pool."""
        self.database_url = database_url
        self._pool = psycopg2.pool.SimpleConnectionPool(1, 5, database_url)
        if not self._pool:
            raise RuntimeError("Failed to create connection pool")
        self.ensure_schema()

    def _get_conn(self):
        """Get a connection from the pool."""
        return self._pool.getconn()

    def _put_conn(self, conn):
        """Return a connection to the pool."""
        self._pool.putconn(conn)

    def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            self._pool.closeall()

    def ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                # Crawl runs table
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS crawl_runs (
                      run_id TEXT PRIMARY KEY,
                      started_at TIMESTAMP WITH TIME ZONE,
                      finished_at TIMESTAMP WITH TIME ZONE,
                      kind TEXT,
                      categories_json TEXT,
                      total_seen INTEGER,
                      added INTEGER,
                      maintained INTEGER,
                      removed INTEGER
                    )
                    """
                )

                # Jobs table
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS jobs (
                      job_uuid TEXT PRIMARY KEY,
                      first_seen_run_id TEXT,
                      last_seen_run_id TEXT,
                      is_active BOOLEAN,
                      first_seen_at TIMESTAMP WITH TIME ZONE,
                      last_seen_at TIMESTAMP WITH TIME ZONE,
                      title TEXT,
                      company_name TEXT,
                      location TEXT,
                      description TEXT,
                      raw_json JSONB
                    )
                    """
                )

                # Job run status table
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS job_run_status (
                      run_id TEXT,
                      job_uuid TEXT,
                      status TEXT,
                      PRIMARY KEY (run_id, job_uuid)
                    )
                    """
                )

                # Indexes
                cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_active ON jobs(is_active)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs(last_seen_at DESC)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_crawl_runs_finished ON crawl_runs(finished_at DESC)")

                conn.commit()
        finally:
            self._put_conn(conn)

    def begin_run(self, *, kind: str, categories: Sequence[str] | None) -> RunStats:
        """Begin a new crawl run."""
        started_at = _utcnow()
        run_id = started_at.strftime("%Y%m%dT%H%M%S.%fZ")
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO crawl_runs(run_id, started_at, finished_at, kind, categories_json,
                                          total_seen, added, maintained, removed)
                    VALUES (%s, %s, NULL, %s, %s, 0, 0, 0, 0)
                    """,
                    [run_id, started_at, kind, json.dumps(list(categories) if categories else [])],
                )
                conn.commit()
        finally:
            self._put_conn(conn)

        return RunStats(
            run_id=run_id,
            started_at=started_at,
            finished_at=None,
            total_seen=0,
            added=0,
            maintained=0,
            removed=0,
        )

    def finish_run(
        self, run_id: str, *, total_seen: int, added: int, maintained: int, removed: int
    ) -> None:
        """Finish a crawl run with statistics."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE crawl_runs
                       SET finished_at = %s,
                           total_seen = %s,
                           added = %s,
                           maintained = %s,
                           removed = %s
                     WHERE run_id = %s
                    """,
                    [_utcnow(), total_seen, added, maintained, removed, run_id],
                )
                conn.commit()
        finally:
            self._put_conn(conn)

    def existing_job_uuids(self) -> set[str]:
        """Get set of all existing job UUIDs."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT job_uuid FROM jobs")
                rows = cur.fetchall()
                return {r[0] for r in rows}
        finally:
            self._put_conn(conn)

    def active_job_uuids(self) -> set[str]:
        """Get set of all active job UUIDs."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT job_uuid FROM jobs WHERE is_active = TRUE")
                rows = cur.fetchall()
                return {r[0] for r in rows}
        finally:
            self._put_conn(conn)

    def record_statuses(
        self, run_id: str, *, added: Iterable[str], maintained: Iterable[str], removed: Iterable[str]
    ) -> None:
        """Record job statuses for a run."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                rows: list[tuple[str, str, str]] = []
                rows.extend((run_id, uuid, "added") for uuid in added)
                rows.extend((run_id, uuid, "maintained") for uuid in maintained)
                rows.extend((run_id, uuid, "removed") for uuid in removed)
                if rows:
                    cur.executemany(
                        "INSERT INTO job_run_status(run_id, job_uuid, status) VALUES (%s, %s, %s) ON CONFLICT (run_id, job_uuid) DO UPDATE SET status = EXCLUDED.status",
                        rows,
                    )
                conn.commit()
        finally:
            self._put_conn(conn)

    def touch_jobs(self, *, run_id: str, job_uuids: Iterable[str]) -> None:
        """Update last_seen timestamp for maintained jobs."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                now = _utcnow()
                rows = [(run_id, now, uuid) for uuid in job_uuids]
                if rows:
                    cur.executemany(
                        "UPDATE jobs SET last_seen_run_id = %s, last_seen_at = %s, is_active = TRUE WHERE job_uuid = %s",
                        rows,
                    )
                conn.commit()
        finally:
            self._put_conn(conn)

    def deactivate_jobs(self, *, run_id: str, job_uuids: Iterable[str]) -> None:
        """Deactivate jobs that were removed."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                now = _utcnow()
                rows = [(run_id, now, uuid) for uuid in job_uuids]
                if rows:
                    cur.executemany(
                        "UPDATE jobs SET last_seen_run_id = %s, last_seen_at = %s, is_active = FALSE WHERE job_uuid = %s",
                        rows,
                    )
                conn.commit()
        finally:
            self._put_conn(conn)

    def upsert_new_job_detail(
        self,
        *,
        run_id: str,
        job_uuid: str,
        title: str | None,
        company_name: str | None,
        location: str | None,
        description: str | None,
        raw_json: dict,
    ) -> None:
        """Insert or update a job detail."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                now = _utcnow()
                # Use json.dumps to convert dict to JSON string, PostgreSQL will handle conversion to JSONB
                cur.execute(
                    """
                    INSERT INTO jobs(job_uuid, first_seen_run_id, last_seen_run_id, is_active,
                                   first_seen_at, last_seen_at,
                                   title, company_name, location, description, raw_json)
                    VALUES (%s, %s, %s, TRUE, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (job_uuid) DO UPDATE SET
                      last_seen_run_id = EXCLUDED.last_seen_run_id,
                      is_active = TRUE,
                      last_seen_at = EXCLUDED.last_seen_at,
                      title = COALESCE(NULLIF(EXCLUDED.title, ''), jobs.title),
                      company_name = COALESCE(NULLIF(EXCLUDED.company_name, ''), jobs.company_name),
                      location = COALESCE(NULLIF(EXCLUDED.location, ''), jobs.location),
                      description = COALESCE(NULLIF(EXCLUDED.description, ''), jobs.description),
                      raw_json = COALESCE(EXCLUDED.raw_json, jobs.raw_json)
                    """,
                    [
                        job_uuid,
                        run_id,
                        run_id,
                        now,
                        now,
                        title,
                        company_name,
                        location,
                        description,
                        json.dumps(raw_json),
                    ],
                )
                conn.commit()
        finally:
            self._put_conn(conn)

    def get_job(self, job_uuid: str) -> dict | None:
        """Get job by UUID."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT job_uuid, title, company_name, location, description, 
                           raw_json::text as raw_json, is_active
                    FROM jobs WHERE job_uuid = %s
                    """,
                    [job_uuid],
                )
                row = cur.fetchone()
                if not row:
                    return None
                result = dict(row)
                # Parse JSON string back to dict if needed
                if result.get("raw_json") and isinstance(result["raw_json"], str):
                    result["raw_json"] = json.loads(result["raw_json"])
                return result
        finally:
            self._put_conn(conn)

    def search_jobs(
        self, *, limit: int = 100, offset: int = 0, category: str | None = None, keywords: str | None = None
    ) -> list[dict]:
        """Search jobs with filters."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                sql = "SELECT job_uuid, title, company_name, location, description FROM jobs WHERE is_active = TRUE"
                params = []
                if category:
                    sql += " AND raw_json::text LIKE %s"
                    params.append(f'%"categories"%{category}%')
                if keywords:
                    sql += " AND (title ILIKE %s OR description ILIKE %s)"
                    params.extend([f"%{keywords}%", f"%{keywords}%"])
                sql += " ORDER BY last_seen_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                cur.execute(sql, params)
                rows = cur.fetchall()
                return [dict(row) for row in rows]
        finally:
            self._put_conn(conn)

    def get_recent_runs(self, limit: int = 10) -> list[dict]:
        """Get recent crawl runs with statistics."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT run_id, started_at, finished_at, total_seen, added, maintained, removed
                    FROM crawl_runs
                    WHERE finished_at IS NOT NULL
                    ORDER BY finished_at DESC
                    LIMIT %s
                    """,
                    [limit],
                )
                rows = cur.fetchall()
                return [dict(row) for row in rows]
        finally:
            self._put_conn(conn)

    def get_active_job_count(self) -> int:
        """Get count of active jobs."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM jobs WHERE is_active = TRUE")
                return cur.fetchone()[0]
        finally:
            self._put_conn(conn)
