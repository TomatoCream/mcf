"""DuckDB-backed storage for incremental crawling and embeddings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import duckdb

from mcf.lib.storage.base import RunStats, Storage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DuckDBStore(Storage):
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
              job_url TEXT
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
        self._con.execute("CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs(last_seen_at DESC)")
        
        # Job interactions table for tracking user interactions
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS job_interactions (
              user_id TEXT,
              job_uuid TEXT,
              interaction_type TEXT,
              interacted_at TIMESTAMP,
              PRIMARY KEY (user_id, job_uuid, interaction_type)
            )
            """
        )
        self._con.execute("CREATE INDEX IF NOT EXISTS idx_job_interactions_user_job ON job_interactions(user_id, job_uuid)")

        # User and profile tables
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              user_id TEXT PRIMARY KEY,
              email TEXT UNIQUE,
              password_hash TEXT,
              created_at TIMESTAMP,
              last_login TIMESTAMP,
              role TEXT
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS candidate_profiles (
              profile_id TEXT PRIMARY KEY,
              user_id TEXT,
              raw_resume_text TEXT,
              expanded_profile_json TEXT,
              skills_json TEXT,
              experience_json TEXT,
              created_at TIMESTAMP,
              updated_at TIMESTAMP
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
              conversation_id TEXT PRIMARY KEY,
              profile_id TEXT,
              messages_json TEXT,
              created_at TIMESTAMP,
              updated_at TIMESTAMP
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS candidate_embeddings (
              profile_id TEXT PRIMARY KEY,
              model_name TEXT,
              embedding_json TEXT,
              dim INTEGER,
              embedded_at TIMESTAMP
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS matches (
              match_id TEXT PRIMARY KEY,
              profile_id TEXT,
              job_uuid TEXT,
              similarity_score FLOAT,
              match_type TEXT,
              created_at TIMESTAMP
            )
            """
        )
        self._con.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        self._con.execute("CREATE INDEX IF NOT EXISTS idx_profiles_user ON candidate_profiles(user_id)")
        self._con.execute("CREATE INDEX IF NOT EXISTS idx_conversations_profile ON conversations(profile_id)")
        self._con.execute("CREATE INDEX IF NOT EXISTS idx_matches_profile ON matches(profile_id)")
        self._con.execute("CREATE INDEX IF NOT EXISTS idx_matches_job ON matches(job_uuid)")

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
        job_url: str | None,
        raw_json: dict | None = None,
    ) -> None:
        now = _utcnow()
        self._con.execute(
            """
            INSERT INTO jobs(job_uuid, first_seen_run_id, last_seen_run_id, is_active,
                             first_seen_at, last_seen_at,
                             title, company_name, location, job_url)
            VALUES (?, ?, ?, TRUE, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (job_uuid) DO UPDATE SET
              last_seen_run_id = excluded.last_seen_run_id,
              is_active = TRUE,
              last_seen_at = excluded.last_seen_at,
              title = COALESCE(excluded.title, jobs.title),
              company_name = COALESCE(excluded.company_name, jobs.company_name),
              location = COALESCE(excluded.location, jobs.location),
              job_url = COALESCE(excluded.job_url, jobs.job_url)
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
                job_url,
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

    def jobs_missing_embeddings(self, *, limit: int | None = None) -> list[str]:
        """Get job UUIDs that are missing embeddings. Note: descriptions are not stored, so this is mainly for migration."""
        sql = """
          SELECT j.job_uuid
            FROM jobs j
       LEFT JOIN job_embeddings e ON e.job_uuid = j.job_uuid
           WHERE j.is_active = TRUE
             AND e.job_uuid IS NULL
        """
        if limit and limit > 0:
            sql += f" LIMIT {int(limit)}"
        rows = self._con.execute(sql).fetchall()
        return [r[0] for r in rows]

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

    def get_active_job_embeddings(self) -> list[tuple[str, str, list[float], dict]]:
        """Get active job embeddings with all job details in a single query.
        
        Returns:
            List of tuples: (job_uuid, title, embedding, job_details_dict)
            where job_details_dict contains: company_name, location, job_url, 
            first_seen_at, last_seen_at
        """
        rows = self._con.execute(
            """
            SELECT j.job_uuid, j.title, e.embedding_json,
                   j.company_name, j.location, j.job_url,
                   j.first_seen_at, j.last_seen_at
              FROM jobs j
              JOIN job_embeddings e ON e.job_uuid = j.job_uuid
             WHERE j.is_active = TRUE
            """
        ).fetchall()
        out: list[tuple[str, str, list[float], dict]] = []
        for uuid, title, emb_json, company_name, location, job_url, first_seen_at, last_seen_at in rows:
            job_details = {
                "company_name": company_name,
                "location": location,
                "job_url": job_url,
                "first_seen_at": first_seen_at,
                "last_seen_at": last_seen_at,
            }
            out.append((uuid, title or "", json.loads(emb_json), job_details))
        return out

    # User management
    def create_user(self, *, user_id: str, email: str, password_hash: str, role: str = "candidate") -> None:
        """Create a new user."""
        now = _utcnow()
        self._con.execute(
            """
            INSERT INTO users(user_id, email, password_hash, created_at, last_login, role)
            VALUES (?, ?, ?, ?, NULL, ?)
            """,
            [user_id, email, password_hash, now, role],
        )

    def get_user_by_email(self, email: str) -> dict | None:
        """Get user by email."""
        row = self._con.execute(
            "SELECT user_id, email, password_hash, role, created_at, last_login FROM users WHERE email = ?",
            [email],
        ).fetchone()
        if not row:
            return None
        return {
            "user_id": row[0],
            "email": row[1],
            "password_hash": row[2],
            "role": row[3],
            "created_at": row[4],
            "last_login": row[5],
        }

    def get_user_by_id(self, user_id: str) -> dict | None:
        """Get user by ID."""
        row = self._con.execute(
            "SELECT user_id, email, password_hash, role, created_at, last_login FROM users WHERE user_id = ?",
            [user_id],
        ).fetchone()
        if not row:
            return None
        return {
            "user_id": row[0],
            "email": row[1],
            "password_hash": row[2],
            "role": row[3],
            "created_at": row[4],
            "last_login": row[5],
        }

    def update_last_login(self, user_id: str) -> None:
        """Update user's last login timestamp."""
        self._con.execute("UPDATE users SET last_login = ? WHERE user_id = ?", [_utcnow(), user_id])

    # Profile management
    def create_profile(
        self,
        *,
        profile_id: str,
        user_id: str,
        raw_resume_text: str | None = None,
        expanded_profile_json: dict | None = None,
        skills_json: list[str] | None = None,
        experience_json: list[dict] | None = None,
    ) -> None:
        """Create a candidate profile."""
        now = _utcnow()
        self._con.execute(
            """
            INSERT INTO candidate_profiles(profile_id, user_id, raw_resume_text, expanded_profile_json,
                                          skills_json, experience_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                profile_id,
                user_id,
                raw_resume_text,
                json.dumps(expanded_profile_json) if expanded_profile_json else None,
                json.dumps(skills_json) if skills_json else None,
                json.dumps(experience_json) if experience_json else None,
                now,
                now,
            ],
        )

    def get_profile_by_user_id(self, user_id: str) -> dict | None:
        """Get profile by user ID."""
        row = self._con.execute(
            """
            SELECT profile_id, user_id, raw_resume_text, expanded_profile_json,
                   skills_json, experience_json, created_at, updated_at
            FROM candidate_profiles WHERE user_id = ?
            """,
            [user_id],
        ).fetchone()
        if not row:
            return None
        return {
            "profile_id": row[0],
            "user_id": row[1],
            "raw_resume_text": row[2],
            "expanded_profile_json": json.loads(row[3]) if row[3] else None,
            "skills_json": json.loads(row[4]) if row[4] else None,
            "experience_json": json.loads(row[5]) if row[5] else None,
            "created_at": row[6],
            "updated_at": row[7],
        }

    def update_profile(
        self,
        *,
        profile_id: str,
        raw_resume_text: str | None = None,
        expanded_profile_json: dict | None = None,
        skills_json: list[str] | None = None,
        experience_json: list[dict] | None = None,
    ) -> None:
        """Update a candidate profile."""
        now = _utcnow()
        updates = []
        values = []
        if raw_resume_text is not None:
            updates.append("raw_resume_text = ?")
            values.append(raw_resume_text)
        if expanded_profile_json is not None:
            updates.append("expanded_profile_json = ?")
            values.append(json.dumps(expanded_profile_json))
        if skills_json is not None:
            updates.append("skills_json = ?")
            values.append(json.dumps(skills_json))
        if experience_json is not None:
            updates.append("experience_json = ?")
            values.append(json.dumps(experience_json))
        updates.append("updated_at = ?")
        values.append(now)
        values.append(profile_id)
        self._con.execute(
            f"UPDATE candidate_profiles SET {', '.join(updates)} WHERE profile_id = ?",
            values,
        )

    # Conversation management
    def create_conversation(self, *, conversation_id: str, profile_id: str, messages: list[dict]) -> None:
        """Create or update a conversation."""
        now = _utcnow()
        self._con.execute(
            """
            INSERT INTO conversations(conversation_id, profile_id, messages_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (conversation_id) DO UPDATE SET
              messages_json = excluded.messages_json,
              updated_at = excluded.updated_at
            """,
            [conversation_id, profile_id, json.dumps(messages), now, now],
        )

    def get_conversation(self, conversation_id: str) -> dict | None:
        """Get conversation by ID."""
        row = self._con.execute(
            "SELECT conversation_id, profile_id, messages_json, created_at, updated_at FROM conversations WHERE conversation_id = ?",
            [conversation_id],
        ).fetchone()
        if not row:
            return None
        return {
            "conversation_id": row[0],
            "profile_id": row[1],
            "messages_json": json.loads(row[2]) if row[2] else [],
            "created_at": row[3],
            "updated_at": row[4],
        }

    def get_conversation_by_profile(self, profile_id: str) -> dict | None:
        """Get conversation by profile ID."""
        row = self._con.execute(
            "SELECT conversation_id, profile_id, messages_json, created_at, updated_at FROM conversations WHERE profile_id = ? ORDER BY updated_at DESC LIMIT 1",
            [profile_id],
        ).fetchone()
        if not row:
            return None
        return {
            "conversation_id": row[0],
            "profile_id": row[1],
            "messages_json": json.loads(row[2]) if row[2] else [],
            "created_at": row[3],
            "updated_at": row[4],
        }

    # Candidate embeddings
    def upsert_candidate_embedding(self, *, profile_id: str, model_name: str, embedding: Sequence[float]) -> None:
        """Store candidate embedding."""
        now = _utcnow()
        emb_list = [float(x) for x in embedding]
        self._con.execute(
            """
            INSERT INTO candidate_embeddings(profile_id, model_name, embedding_json, dim, embedded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (profile_id) DO UPDATE SET
              model_name = excluded.model_name,
              embedding_json = excluded.embedding_json,
              dim = excluded.dim,
              embedded_at = excluded.embedded_at
            """,
            [profile_id, model_name, json.dumps(emb_list), len(emb_list), now],
        )

    def get_candidate_embeddings(self) -> list[tuple[str, list[float]]]:
        """Get all candidate embeddings."""
        rows = self._con.execute(
            "SELECT profile_id, embedding_json FROM candidate_embeddings"
        ).fetchall()
        return [(row[0], json.loads(row[1])) for row in rows]

    def get_candidate_embedding(self, profile_id: str) -> list[float] | None:
        """Get candidate embedding by profile ID."""
        row = self._con.execute(
            "SELECT embedding_json FROM candidate_embeddings WHERE profile_id = ?",
            [profile_id],
        ).fetchone()
        if not row:
            return None
        return json.loads(row[0])

    # Matching
    def record_match(
        self, *, match_id: str, profile_id: str, job_uuid: str, similarity_score: float, match_type: str
    ) -> None:
        """Record a match."""
        now = _utcnow()
        self._con.execute(
            """
            INSERT INTO matches(match_id, profile_id, job_uuid, similarity_score, match_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [match_id, profile_id, job_uuid, similarity_score, match_type, now],
        )

    def get_job(self, job_uuid: str) -> dict | None:
        """Get job by UUID."""
        row = self._con.execute(
            """
            SELECT job_uuid, title, company_name, location, job_url, is_active, first_seen_at, last_seen_at
            FROM jobs WHERE job_uuid = ?
            """,
            [job_uuid],
        ).fetchone()
        if not row:
            return None
        return {
            "job_uuid": row[0],
            "title": row[1],
            "company_name": row[2],
            "location": row[3],
            "job_url": row[4],
            "is_active": row[5],
            "first_seen_at": row[6],
            "last_seen_at": row[7],
        }

    def search_jobs(
        self, *, limit: int = 100, offset: int = 0, category: str | None = None, keywords: str | None = None
    ) -> list[dict]:
        """Search jobs with filters."""
        sql = "SELECT job_uuid, title, company_name, location, job_url FROM jobs WHERE is_active = TRUE"
        params = []
        if keywords:
            sql += " AND (title LIKE ? OR company_name LIKE ? OR location LIKE ?)"
            params.extend([f"%{keywords}%", f"%{keywords}%", f"%{keywords}%"])
        sql += " ORDER BY last_seen_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._con.execute(sql, params).fetchall()
        return [
            {
                "job_uuid": row[0],
                "title": row[1],
                "company_name": row[2],
                "location": row[3],
                "job_url": row[4],
            }
            for row in rows
        ]

    def get_recent_runs(self, limit: int = 10) -> list[dict]:
        """Get recent crawl runs with statistics."""
        rows = self._con.execute(
            """
            SELECT run_id, started_at, finished_at, total_seen, added, maintained, removed
            FROM crawl_runs
            WHERE finished_at IS NOT NULL
            ORDER BY finished_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
        return [
            {
                "run_id": row[0],
                "started_at": row[1],
                "finished_at": row[2],
                "total_seen": row[3],
                "added": row[4],
                "maintained": row[5],
                "removed": row[6],
            }
            for row in rows
        ]

    def get_active_job_count(self) -> int:
        """Get count of active jobs."""
        row = self._con.execute("SELECT COUNT(*) FROM jobs WHERE is_active = TRUE").fetchone()
        return row[0] if row else 0

    # Job interaction tracking
    def record_interaction(self, *, user_id: str, job_uuid: str, interaction_type: str) -> None:
        """Record a user interaction with a job."""
        now = _utcnow()
        self._con.execute(
            """
            INSERT OR REPLACE INTO job_interactions(user_id, job_uuid, interaction_type, interacted_at)
            VALUES (?, ?, ?, ?)
            """,
            [user_id, job_uuid, interaction_type, now],
        )

    def get_interacted_jobs(self, user_id: str) -> set[str]:
        """Get set of job UUIDs that the user has interacted with."""
        rows = self._con.execute(
            "SELECT DISTINCT job_uuid FROM job_interactions WHERE user_id = ?",
            [user_id],
        ).fetchall()
        return {row[0] for row in rows}

    def has_interacted(self, user_id: str, job_uuid: str) -> bool:
        """Check if user has interacted with a job."""
        row = self._con.execute(
            "SELECT 1 FROM job_interactions WHERE user_id = ? AND job_uuid = ? LIMIT 1",
            [user_id, job_uuid],
        ).fetchone()
        return row is not None

    def get_profile_by_profile_id(self, profile_id: str) -> dict | None:
        """Get profile by profile ID."""
        row = self._con.execute(
            """
            SELECT profile_id, user_id, raw_resume_text, expanded_profile_json,
                   skills_json, experience_json, created_at, updated_at
            FROM candidate_profiles WHERE profile_id = ?
            """,
            [profile_id],
        ).fetchone()
        if not row:
            return None
        return {
            "profile_id": row[0],
            "user_id": row[1],
            "raw_resume_text": row[2],
            "expanded_profile_json": json.loads(row[3]) if row[3] else None,
            "skills_json": json.loads(row[4]) if row[4] else None,
            "experience_json": json.loads(row[5]) if row[5] else None,
            "created_at": row[6],
            "updated_at": row[7],
        }
