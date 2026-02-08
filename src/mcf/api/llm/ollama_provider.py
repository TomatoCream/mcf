"""Ollama LLM provider (local/open source)."""

from __future__ import annotations

import httpx

from mcf.api.config import settings
from mcf.api.llm.provider import LLMProvider


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider."""

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Send chat message to Ollama."""
        # Convert messages to Ollama format
        ollama_messages = []
        for msg in messages:
            if msg["role"] != "system":  # Ollama doesn't use system messages the same way
                ollama_messages.append({"role": msg["role"], "content": msg["content"]})

        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": ollama_messages,
                    "stream": False,
                },
            )
            response.raise_for_status()
            return response.json()["message"]["content"]

    def stream_chat(self, messages: list[dict[str, str]], **kwargs):
        """Stream chat responses from Ollama."""
        ollama_messages = []
        for msg in messages:
            if msg["role"] != "system":
                ollama_messages.append({"role": msg["role"], "content": msg["content"]})

        with httpx.Client(timeout=120.0) as client:
            with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": ollama_messages,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        import json

                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]
