"""FastAPI server."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pathlib import Path

from mcf.api.config import settings
from mcf.api.services.matching_service import MatchingService
from mcf.lib.embeddings.embedder import Embedder, EmbedderConfig
from mcf.lib.embeddings.resume import extract_resume_text
from mcf.lib.storage.base import Storage
from mcf.lib.storage.duckdb_store import DuckDBStore

# Global store instance
_store: Storage | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI."""
    global _store
    # Ensure data directory exists
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _store = DuckDBStore(settings.db_path)
    yield
    if _store:
        _store.close()


app = FastAPI(title="MCF Job Crawler API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_store() -> Storage:
    """Get storage instance."""
    if _store is None:
        raise RuntimeError("Store not initialized")
    return _store


# Job endpoints
@app.get("/api/jobs")
def list_jobs(
    limit: int = 100,
    offset: int = 0,
    keywords: str | None = None,
    exclude_interacted: bool = True,
):
    """List jobs with optional filters."""
    store = get_store()
    user_id = settings.default_user_id
    
    jobs = store.search_jobs(limit=limit * 2, offset=offset, keywords=keywords)  # Get more to filter
    
    # Filter out interacted jobs if requested
    if exclude_interacted:
        interacted = store.get_interacted_jobs(user_id)
        jobs = [j for j in jobs if j["job_uuid"] not in interacted]
    
    # Limit after filtering
    jobs = jobs[:limit]
    return {"jobs": jobs, "total": len(jobs)}


@app.get("/api/jobs/{job_uuid}")
def get_job(job_uuid: str):
    """Get job basic info by UUID (no description stored)."""
    store = get_store()
    job = store.get_job(job_uuid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check if user has interacted with this job
    user_id = settings.default_user_id
    interactions = []
    if isinstance(store, DuckDBStore):
        rows = store._con.execute(
            "SELECT interaction_type FROM job_interactions WHERE user_id = ? AND job_uuid = ?",
            [user_id, job_uuid],
        ).fetchall()
        interactions = [row[0] for row in rows]
    
    job["interactions"] = interactions
    return job


@app.post("/api/jobs/{job_uuid}/interact")
def mark_interaction(
    job_uuid: str,
    interaction_type: str = Query(..., description="Interaction type: viewed, dismissed, applied, saved"),
):
    """Mark a job as interacted with."""
    store = get_store()
    user_id = settings.default_user_id
    
    if interaction_type not in ["viewed", "dismissed", "applied", "saved"]:
        raise HTTPException(status_code=400, detail="Invalid interaction type")
    
    # Verify job exists
    job = store.get_job(job_uuid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    store.record_interaction(user_id=user_id, job_uuid=job_uuid, interaction_type=interaction_type)
    return {"status": "ok", "job_uuid": job_uuid, "interaction_type": interaction_type}


# Profile endpoints
@app.get("/api/profile")
def get_profile():
    """Get current user profile and resume status."""
    store = get_store()
    user_id = settings.default_user_id
    
    profile = store.get_profile_by_user_id(user_id)
    resume_path = Path(settings.resume_path)
    resume_exists = resume_path.exists()
    
    return {
        "user_id": user_id,
        "profile": profile,
        "resume_path": str(resume_path),
        "resume_exists": resume_exists,
    }


@app.post("/api/profile/process-resume")
def process_resume():
    """Process resume from file path and create/update profile."""
    store = get_store()
    user_id = settings.default_user_id
    resume_path = Path(settings.resume_path)
    
    if not resume_path.exists():
        raise HTTPException(status_code=404, detail=f"Resume file not found at {resume_path}")
    
    try:
        # Extract resume text
        resume_text = extract_resume_text(resume_path)
        
        # Get or create profile
        profile = store.get_profile_by_user_id(user_id)
        if profile:
            profile_id = profile["profile_id"]
            store.update_profile(profile_id=profile_id, raw_resume_text=resume_text)
        else:
            # Create new profile
            import secrets
            profile_id = secrets.token_urlsafe(16)
            store.create_profile(
                profile_id=profile_id,
                user_id=user_id,
                raw_resume_text=resume_text,
            )
        
        # Generate embedding directly from resume text
        embedder = Embedder(EmbedderConfig())
        embedding = embedder.embed_text(resume_text)
        store.upsert_candidate_embedding(
            profile_id=profile_id,
            model_name=embedder.model_name,
            embedding=embedding,
        )
        
        return {
            "status": "ok",
            "profile_id": profile_id,
            "message": "Resume processed successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process resume: {str(e)}")


# Matching endpoints
@app.get("/api/matches")
def get_matches(exclude_interacted: bool = True, top_k: int = 25):
    """Get job matches for current user's resume."""
    store = get_store()
    user_id = settings.default_user_id
    
    # Get profile
    profile = store.get_profile_by_user_id(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="No profile found. Please process your resume first.")
    
    profile_id = profile["profile_id"]
    
    # Get matches
    matching_service = MatchingService(store)
    matches = matching_service.match_candidate_to_jobs(
        profile_id=profile_id,
        top_k=top_k,
        exclude_interacted=exclude_interacted,
        user_id=user_id,
    )
    
    return {"matches": matches, "total": len(matches)}


@app.get("/api/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}
