"""LLM provider factory."""

from __future__ import annotations

from mcf.api.config import settings
from mcf.api.llm.anthropic_provider import AnthropicProvider
from mcf.api.llm.ollama_provider import OllamaProvider
from mcf.api.llm.openai_provider import OpenAIProvider
from mcf.api.llm.provider import LLMProvider


def get_llm_provider() -> LLMProvider:
    """Get the configured LLM provider."""
    provider_name = settings.llm_provider.lower()
    if provider_name == "openai":
        return OpenAIProvider()
    elif provider_name == "anthropic":
        return AnthropicProvider()
    elif provider_name == "ollama":
        return OllamaProvider()
    else:
        raise ValueError(f"Unknown LLM provider: {provider_name}")
