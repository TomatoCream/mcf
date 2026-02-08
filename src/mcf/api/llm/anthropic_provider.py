"""Anthropic Claude LLM provider."""

from __future__ import annotations

from mcf.api.config import settings
from mcf.api.llm.provider import LLMProvider


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        from anthropic import Anthropic

        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Send chat message to Anthropic."""
        # Convert to Anthropic format
        system_msg = None
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                anthropic_messages.append(
                    {
                        "role": msg["role"],
                        "content": msg["content"],
                    }
                )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_msg or "",
            messages=anthropic_messages,
            **kwargs,
        )
        return response.content[0].text

    def stream_chat(self, messages: list[dict[str, str]], **kwargs):
        """Stream chat responses from Anthropic."""
        system_msg = None
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                anthropic_messages.append(
                    {
                        "role": msg["role"],
                        "content": msg["content"],
                    }
                )

        with self.client.messages.stream(
            model=self.model,
            max_tokens=4096,
            system=system_msg or "",
            messages=anthropic_messages,
            **kwargs,
        ) as stream:
            for text in stream.text_stream:
                yield text
