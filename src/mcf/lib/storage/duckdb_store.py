"""DuckDB-backed storage for incremental crawling and embeddings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import duckdb


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class RunStats:
    run_id: str
    started_at: datetime
    finished_at: datetime | None
    total_seen: int
    added: int
    maintained: int
    removed: int


class DuckDBStore:
    """Persistence layer for incremental crawl state."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._con = duckdb.connect(self.db_path)
        self._con.execute("PRAGMA threads=4")
        self.ensure_schema()

    def close(self) -> None:
        self._con.close()

    def ensure_schema(self) -> None:
        # Note: keep schema simple and portable; store large/variable structures as JSON.
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS crawl_runs (
              run_id TEXT PRIMARY KEY,
              started_at TIMESTAMP,
              finished_at TIMESTAMP,
              kind TEXT,
              categories_json TEXT,
              total_seen INTEGER,
              added INTEGER,
              maintained INTEGER,
              removed INTEGER
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              job_uuid TEXT PRIMARY KEY,
              first_seen_run_id TEXT,
              last_seen_run_id TEXT,
              is_active BOOLEAN,
              first_seen_at TIMESTAMP,
              last_seen_at TIMESTAMP,
              title TEXT,
              company_name TEXT,
              location TEXT,
              description TEXT,
              raw_json TEXT
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS job_run_status (
              run_id TEXT,
              job_uuid TEXT,
              status TEXT,
              PRIMARY KEY (run_id, job_uuid)
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS job_embeddings (
              job_uuid TEXT PRIMARY KEY,
              model_name TEXT,
              embedding_json TEXT,
              dim INTEGER,
              embedded_at TIMESTAMP
            )
            """
        )
        self._con.execute("CREATE INDEX IF NOT EXISTS idx_jobs_active ON jobs(is_active)")

    def begin_run(self, *, kind: str, categories: Sequence[str] | None) -> RunStats:
        started_at = _utcnow()
        run_id = started_at.strftime("%Y%m%dT%H%M%S.%fZ")
        self._con.execute(
            """
            INSERT INTO crawl_runs(run_id, started_at, finished_at, kind, categories_json,
                                  total_seen, added, maintained, removed)
            VALUES (?, ?, NULL, ?, ?, 0, 0, 0, 0)
            """,
            [run_id, started_at, kind, json.dumps(list(categories) if categories else [])],
        )
        return RunStats(
            run_id=run_id,
            started_at=started_at,
            finished_at=None,
            total_seen=0,
            added=0,
            maintained=0,
            removed=0,
        )

    def finish_run(self, run_id: str, *, total_seen: int, added: int, maintained: int, removed: int) -> None:
        self._con.execute(
            """
            UPDATE crawl_runs
               SET finished_at = ?,
                   total_seen = ?,
                   added = ?,
                   maintained = ?,
                   removed = ?
             WHERE run_id = ?
            """,
            [_utcnow(), total_seen, added, maintained, removed, run_id],
        )

    def existing_job_uuids(self) -> set[str]:
        rows = self._con.execute("SELECT job_uuid FROM jobs").fetchall()
        return {r[0] for r in rows}

    def active_job_uuids(self) -> set[str]:
        rows = self._con.execute("SELECT job_uuid FROM jobs WHERE is_active = TRUE").fetchall()
        return {r[0] for r in rows}

    def record_statuses(self, run_id: str, *, added: Iterable[str], maintained: Iterable[str], removed: Iterable[str]) -> None:
        # Batch insert for speed
        rows: list[tuple[str, str, str]] = []
        rows.extend((run_id, uuid, "added") for uuid in added)
        rows.extend((run_id, uuid, "maintained") for uuid in maintained)
        rows.extend((run_id, uuid, "removed") for uuid in removed)
        if not rows:
            return
        self._con.executemany(
            "INSERT OR REPLACE INTO job_run_status(run_id, job_uuid, status) VALUES (?, ?, ?)",
            rows,
        )

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
        now = _utcnow()
        self._con.execute(
            """
            INSERT INTO jobs(job_uuid, first_seen_run_id, last_seen_run_id, is_active,
                             first_seen_at, last_seen_at,
                             title, company_name, location, description, raw_json)
            VALUES (?, ?, ?, TRUE, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (job_uuid) DO UPDATE SET
              last_seen_run_id = excluded.last_seen_run_id,
              is_active = TRUE,
              last_seen_at = excluded.last_seen_at,
              title = COALESCE(excluded.title, jobs.title),
              company_name = COALESCE(excluded.company_name, jobs.company_name),
              location = COALESCE(excluded.location, jobs.location),
              description = COALESCE(excluded.description, jobs.description),
              raw_json = COALESCE(excluded.raw_json, jobs.raw_json)
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
                json.dumps(raw_json, ensure_ascii=False),
            ],
        )

    def touch_jobs(self, *, run_id: str, job_uuids: Iterable[str]) -> None:
        now = _utcnow()
        rows = [(run_id, now, uuid) for uuid in job_uuids]
        if not rows:
            return
        self._con.executemany(
            "UPDATE jobs SET last_seen_run_id = ?, last_seen_at = ?, is_active = TRUE WHERE job_uuid = ?",
            rows,
        )

    def deactivate_jobs(self, *, run_id: str, job_uuids: Iterable[str]) -> None:
        now = _utcnow()
        rows = [(run_id, now, uuid) for uuid in job_uuids]
        if not rows:
            return
        self._con.executemany(
            "UPDATE jobs SET last_seen_run_id = ?, last_seen_at = ?, is_active = FALSE WHERE job_uuid = ?",
            rows,
        )

    def jobs_missing_embeddings(self, *, limit: int | None = None) -> list[tuple[str, str | None]]:
        sql = """
          SELECT j.job_uuid, j.description
            FROM jobs j
       LEFT JOIN job_embeddings e ON e.job_uuid = j.job_uuid
           WHERE j.is_active = TRUE
             AND e.job_uuid IS NULL
             AND j.description IS NOT NULL
        """
        if limit and limit > 0:
            sql += f" LIMIT {int(limit)}"
        rows = self._con.execute(sql).fetchall()
        return [(r[0], r[1]) for r in rows]

    def upsert_embedding(self, *, job_uuid: str, model_name: str, embedding: Sequence[float]) -> None:
        now = _utcnow()
        emb_list = [float(x) for x in embedding]
        self._con.execute(
            """
            INSERT INTO job_embeddings(job_uuid, model_name, embedding_json, dim, embedded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (job_uuid) DO UPDATE SET
              model_name = excluded.model_name,
              embedding_json = excluded.embedding_json,
              dim = excluded.dim,
              embedded_at = excluded.embedded_at
            """,
            [job_uuid, model_name, json.dumps(emb_list), len(emb_list), now],
        )

    def get_active_job_embeddings(self) -> list[tuple[str, str, list[float]]]:
        rows = self._con.execute(
            """
            SELECT j.job_uuid, j.title, e.embedding_json
              FROM jobs j
              JOIN job_embeddings e ON e.job_uuid = j.job_uuid
             WHERE j.is_active = TRUE
            """
        ).fetchall()
        out: list[tuple[str, str, list[float]]] = []
        for uuid, title, emb_json in rows:
            out.append((uuid, title or "", json.loads(emb_json)))
        return out

