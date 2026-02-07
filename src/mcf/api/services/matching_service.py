"""Matching service for bidirectional job-candidate matching."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

import numpy as np

from mcf.lib.storage.duckdb_store import DuckDBStore


class MatchingService:
    """Service for matching candidates to jobs and vice versa."""

    def __init__(self, store: DuckDBStore) -> None:
        self.store = store

    def match_candidate_to_jobs(
        self, profile_id: str, top_k: int = 25, exclude_interacted: bool = True, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Find top matching jobs for a candidate.
        
        Args:
            profile_id: Candidate profile ID
            top_k: Number of top matches to return
            exclude_interacted: If True, filter out jobs user has interacted with
            user_id: User ID for interaction filtering (if None, uses profile's user_id)
        """
        candidate_emb = self.store.get_candidate_embedding(profile_id)
        if not candidate_emb:
            return []

        job_embeddings = self.store.get_active_job_embeddings()
        if not job_embeddings:
            return []

        # Get interacted jobs if filtering is enabled
        interacted_jobs: set[str] = set()
        if exclude_interacted:
            if user_id is None:
                # Get user_id from profile
                profile = self.store.get_profile_by_profile_id(profile_id)
                if profile:
                    user_id = profile.get("user_id")
            if user_id:
                interacted_jobs = self.store.get_interacted_jobs(user_id)

        candidate_vec = np.array(candidate_emb, dtype=np.float32)
        scored: list[tuple[float, str, str, datetime | None]] = []

        for job_uuid, title, job_emb in job_embeddings:
            # Skip interacted jobs if filtering is enabled
            if exclude_interacted and job_uuid in interacted_jobs:
                continue
            
            job_vec = np.array(job_emb, dtype=np.float32)
            # Cosine similarity (embeddings are normalized)
            score = float(np.dot(candidate_vec, job_vec))
            
            # Get job to access last_seen_at for recency sorting
            job = self.store.get_job(job_uuid)
            last_seen_at = job.get("last_seen_at") if job else None
            
            scored.append((score, job_uuid, title, last_seen_at))

        # Sort by: 1) similarity score (desc), 2) recency (newer first)
        # Handle None dates by putting them last (use a very old date)
        def sort_key(x):
            score, _, _, last_seen = x
            # Use a very old date for None to put them last
            date_for_sort = last_seen if last_seen else datetime(1970, 1, 1)
            return (score, date_for_sort)
        
        scored.sort(reverse=True, key=sort_key)
        top_matches = scored[:top_k]

        # Get full job details and record matches
        results = []
        for score, job_uuid, title, _ in top_matches:
            job = self.store.get_job(job_uuid)
            if job:
                match_id = secrets.token_urlsafe(16)
                self.store.record_match(
                    match_id=match_id,
                    profile_id=profile_id,
                    job_uuid=job_uuid,
                    similarity_score=score,
                    match_type="candidate_initiated",
                )
                results.append(
                    {
                        "job_uuid": job_uuid,
                        "title": title or job.get("title"),
                        "company_name": job.get("company_name"),
                        "location": job.get("location"),
                        "job_url": job.get("job_url"),
                        "similarity_score": score,
                        "last_seen_at": job.get("last_seen_at"),
                    }
                )

        return results

    def match_job_to_candidates(self, job_uuid: str, top_k: int = 25) -> list[dict[str, Any]]:
        """Find top matching candidates for a job."""
        job_embeddings = self.store.get_active_job_embeddings()
        job_emb = None
        for uuid, _, emb in job_embeddings:
            if uuid == job_uuid:
                job_emb = emb
                break

        if not job_emb:
            return []

        candidate_embeddings = self.store.get_candidate_embeddings()
        if not candidate_embeddings:
            return []

        job_vec = np.array(job_emb, dtype=np.float32)
        scored: list[tuple[float, str]] = []

        for profile_id, cand_emb in candidate_embeddings:
            cand_vec = np.array(cand_emb, dtype=np.float32)
            score = float(np.dot(job_vec, cand_vec))
            scored.append((score, profile_id))

        scored.sort(reverse=True, key=lambda x: x[0])
        top_matches = scored[:top_k]

        # Get profile details
        results = []
        for score, profile_id in top_matches:
            profile = self.store.get_profile_by_user_id(
                self.store.get_profile_by_user_id(profile_id)["user_id"] if profile_id else None
            )
            if profile:
                match_id = secrets.token_urlsafe(16)
                self.store.record_match(
                    match_id=match_id,
                    profile_id=profile_id,
                    job_uuid=job_uuid,
                    similarity_score=score,
                    match_type="recruiter_search",
                )
                results.append(
                    {
                        "profile_id": profile_id,
                        "skills": profile.get("skills_json", []),
                        "experience": profile.get("experience_json", []),
                        "summary": profile.get("expanded_profile_json", {}).get("summary", ""),
                        "similarity_score": score,
                    }
                )

        return results

    def search_candidates_by_skills(
        self, skills: list[str], top_k: int = 25
    ) -> list[dict[str, Any]]:
        """Search candidates by skills (keyword + semantic matching)."""
        # Get all candidate embeddings
        candidate_embeddings = self.store.get_candidate_embeddings()
        if not candidate_embeddings:
            return []

        # Simple keyword matching for now (can be enhanced with embeddings)
        results = []
        skills_lower = [s.lower() for s in skills]

        for profile_id, _ in candidate_embeddings:
            profile = self.store.get_profile_by_profile_id(profile_id)
            if not profile:
                continue

            profile_skills = profile.get("skills_json", [])
            profile_skills_lower = [s.lower() for s in profile_skills]

            # Count matching skills
            matches = sum(1 for skill in skills_lower if any(skill in ps for ps in profile_skills_lower))
            if matches > 0:
                score = matches / len(skills) if skills else 0
                results.append(
                    {
                        "profile_id": profile_id,
                        "skills": profile_skills,
                        "experience": profile.get("experience_json", []),
                        "summary": profile.get("expanded_profile_json", {}).get("summary", ""),
                        "match_score": score,
                        "matched_skills": matches,
                    }
                )

        results.sort(reverse=True, key=lambda x: x["match_score"])
        return results[:top_k]
