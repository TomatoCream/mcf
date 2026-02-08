"""Text embedding utilities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmbedderConfig:
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    batch_size: int = 32


class Embedder:
    """SentenceTransformers-based embedder.

    Kept behind a small wrapper so the rest of the codebase doesn't depend on
    sentence-transformers directly.
    """

    def __init__(self, config: EmbedderConfig | None = None) -> None:
        self.config = config or EmbedderConfig()
        # Import lazily so the base crawler can run without embedding deps installed.
        from sentence_transformers import SentenceTransformer  # type: ignore

        self._model = SentenceTransformer(self.config.model_name)

    @property
    def model_name(self) -> str:
        return self.config.model_name

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        # Returns numpy array; convert to pure Python lists for storage.
        vectors = self._model.encode(
            texts,
            batch_size=self.config.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

