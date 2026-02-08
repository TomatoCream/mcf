"""API configuration."""

from __future__ import annotations

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Database
    db_path: str = os.getenv("DB_PATH", "data/mcf.duckdb")
    
    # User
    default_user_id: str = os.getenv("DEFAULT_USER_ID", "default_user")
    
    # Resume
    resume_path: str = os.getenv("RESUME_PATH", "resume/resume.pdf")
    
    # API
    api_port: int = int(os.getenv("API_PORT", "8000"))
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
