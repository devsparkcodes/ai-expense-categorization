"""Local embedding model wrapper.

Loads and caches the sentence-transformers model and exposes an embedding helper.
"""

import os

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

_MODEL_NAME = os.environ.get(
    "RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Return the cached embedding model, loading it once on first use."""
    global _model
    if _model is None:
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def embed_text(text: str) -> list[float]:
    """Embed a single piece of text and return the vector as a Python list.

    Raises:
        ValueError: if `text` is empty.
    """
    if not text or not text.strip():
        raise ValueError("Cannot embed an empty string.")
    vector = _get_model().encode(text)
    return vector.tolist()