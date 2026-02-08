"""Abstract LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Send a chat message and get a response.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                     Roles: 'system', 'user', 'assistant'
            **kwargs: Provider-specific parameters
        
        Returns:
            Assistant's response text
        """
        pass

    @abstractmethod
    def stream_chat(self, messages: list[dict[str, str]], **kwargs):
        """Stream chat responses (generator).
        
        Yields:
            Chunks of response text
        """
        pass
