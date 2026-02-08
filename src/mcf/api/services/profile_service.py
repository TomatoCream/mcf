"""Profile service for managing candidate profiles."""

from __future__ import annotations

import secrets
from typing import Any

from mcf.api.llm.factory import get_llm_provider
from mcf.lib.embeddings.embedder import Embedder, EmbedderConfig
from mcf.lib.storage.duckdb_store import DuckDBStore


class ProfileService:
    """Service for managing candidate profiles and LLM conversations."""

    def __init__(self, store: DuckDBStore) -> None:
        self.store = store
        self.llm = get_llm_provider()
        self.embedder = Embedder(EmbedderConfig())

    def create_profile(self, user_id: str, raw_resume_text: str | None = None) -> str:
        """Create a new profile for a user."""
        profile_id = secrets.token_urlsafe(16)
        self.store.create_profile(profile_id=profile_id, user_id=user_id, raw_resume_text=raw_resume_text)
        return profile_id

    def get_profile(self, user_id: str) -> dict[str, Any] | None:
        """Get profile for a user."""
        return self.store.get_profile_by_user_id(user_id)

    def get_or_create_conversation(self, profile_id: str) -> str:
        """Get existing conversation or create a new one."""
        conv = self.store.get_conversation_by_profile(profile_id)
        if conv:
            return conv["conversation_id"]
        conversation_id = secrets.token_urlsafe(16)
        # Initialize with system message
        messages = [
            {
                "role": "system",
                "content": """You are a helpful career advisor helping to build a comprehensive candidate profile.
Ask questions about their work experience, skills, achievements, and career goals.
Extract and structure information about:
- Work history with detailed responsibilities
- Technical and soft skills
- Achievements and impact
- Education and certifications
- Career aspirations

Be conversational and ask follow-up questions to get rich details.""",
            }
        ]
        self.store.create_conversation(conversation_id=conversation_id, profile_id=profile_id, messages=messages)
        return conversation_id

    def chat(self, conversation_id: str, user_message: str) -> str:
        """Send a message in the conversation and get LLM response."""
        conv = self.store.get_conversation(conversation_id)
        if not conv:
            raise ValueError(f"Conversation {conversation_id} not found")

        messages = conv["messages_json"]
        messages.append({"role": "user", "content": user_message})

        # Get LLM response
        response = self.llm.chat(messages)

        messages.append({"role": "assistant", "content": response})
        self.store.create_conversation(conversation_id=conversation_id, profile_id=conv["profile_id"], messages=messages)

        return response

    def stream_chat(self, conversation_id: str, user_message: str):
        """Stream chat response."""
        conv = self.store.get_conversation(conversation_id)
        if not conv:
            raise ValueError(f"Conversation {conversation_id} not found")

        messages = conv["messages_json"]
        messages.append({"role": "user", "content": user_message})

        # Stream LLM response
        full_response = ""
        for chunk in self.llm.stream_chat(messages):
            full_response += chunk
            yield chunk

        messages.append({"role": "assistant", "content": full_response})
        self.store.create_conversation(conversation_id=conversation_id, profile_id=conv["profile_id"], messages=messages)

    def extract_profile_data(self, conversation_id: str) -> dict[str, Any]:
        """Extract structured profile data from conversation using LLM."""
        conv = self.store.get_conversation(conversation_id)
        if not conv:
            raise ValueError(f"Conversation {conversation_id} not found")

        messages = conv["messages_json"]
        extraction_prompt = {
            "role": "user",
            "content": """Based on our conversation, extract and structure the candidate's profile as JSON:
{
  "skills": ["skill1", "skill2", ...],
  "experience": [
    {
      "title": "Job Title",
      "company": "Company Name",
      "duration": "Duration",
      "responsibilities": ["responsibility1", ...],
      "achievements": ["achievement1", ...]
    }
  ],
  "education": [...],
  "summary": "Brief professional summary"
}

Return only valid JSON.""",
        }
        messages.append(extraction_prompt)
        response = self.llm.chat(messages)

        # Try to parse JSON from response
        import json
        import re

        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            try:
                profile_data = json.loads(json_match.group())
                return profile_data
            except json.JSONDecodeError:
                pass

        # Fallback: return raw response
        return {"raw_extraction": response}

    def finalize_profile(self, profile_id: str, conversation_id: str) -> None:
        """Finalize profile by extracting data and generating embedding."""
        profile_data = self.extract_profile_data(conversation_id)
        profile = self.store.get_profile_by_user_id(self.store.get_profile_by_user_id(profile_id)["user_id"])

        # Update profile with extracted data
        skills = profile_data.get("skills", [])
        experience = profile_data.get("experience", [])
        self.store.update_profile(
            profile_id=profile_id,
            expanded_profile_json=profile_data,
            skills_json=skills,
            experience_json=experience,
        )

        # Generate embedding from profile text
        profile_text = self._build_profile_text(profile_data)
        embedding = self.embedder.embed_text(profile_text)
        self.store.upsert_candidate_embedding(
            profile_id=profile_id, model_name=self.embedder.model_name, embedding=embedding
        )

    def _build_profile_text(self, profile_data: dict[str, Any]) -> str:
        """Build a text representation of the profile for embedding."""
        parts = []
        if "summary" in profile_data:
            parts.append(profile_data["summary"])
        if "skills" in profile_data:
            parts.append("Skills: " + ", ".join(profile_data["skills"]))
        if "experience" in profile_data:
            for exp in profile_data["experience"]:
                parts.append(f"{exp.get('title', '')} at {exp.get('company', '')}")
                if "responsibilities" in exp:
                    parts.extend(exp["responsibilities"])
                if "achievements" in exp:
                    parts.extend(exp["achievements"])
        return "\n".join(parts)
