"""Schemas for the RAG retrieval layer."""

from typing import List, Optional

from pydantic import BaseModel


class RetrievalResult(BaseModel):
    """Structured result returned by the RAG retriever."""

    category: str
    confidence: float
    source: str
    matched_merchant: str
    document_id: str


class RAGContextItem(BaseModel):
    """A single retrieved knowledge item passed to the AI categorizer."""

    merchant: str
    category: str
    confidence: float
    source: str


class RAGCategorizeResult(BaseModel):
    """Result of a RAG categorization attempt.

    On a strong match, `category` is set and `source` is "rag".
    On a weak match, `category` is None and `source` is "rag_context",
    with `context` carrying the retrieved examples for the AI categorizer.
    """

    category: Optional[str] = None
    confidence: float
    source: str
    matched_merchant: str
    context: List[RAGContextItem] = []