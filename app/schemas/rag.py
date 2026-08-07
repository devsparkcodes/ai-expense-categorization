"""Schemas for the RAG retrieval layer."""

from pydantic import BaseModel


class RetrievalResult(BaseModel):
    """Structured result returned by the RAG retriever."""

    category: str
    confidence: float
    source: str
    matched_merchant: str