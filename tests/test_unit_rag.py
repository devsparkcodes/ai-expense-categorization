"""Unit tests for the RAG retrieval layer (retriever, embedder, rag_service).

Isolation guarantees:
- No persistent data/vector_store is created or touched.
- No sentence-transformers model is actually loaded.
- No OpenRouter/LLM calls are made.
The Chroma collection and embeddings are mocked with lightweight fakes.
"""

import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from app.schemas.rag import RetrievalResult
from app.services import rag_service
from app.vector_db import embedder, retriever


class FakeCollection:
    """Minimal stand-in for a Chroma collection backed by in-memory docs."""

    def __init__(self, docs):
        self._docs = docs

    def count(self):
        return len(self._docs)

    def query(self, query_embeddings, n_results, include):
        query_vec = query_embeddings[0]
        scored = sorted(
            self._docs,
            key=lambda d: _cosine(query_vec, d["embedding"]),
            reverse=True,
        )[:n_results]
        return {
            "ids": [[d["id"] for d in scored]],
            "metadatas": [[d["metadata"] for d in scored]],
            "documents": [[d["document"] for d in scored]],
            "embeddings": [[d["embedding"] for d in scored]],
        }


def _cosine(a, b):
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def _make_doc(doc_id, merchant, category, source, embedding):
    return {
        "id": doc_id,
        "metadata": {"merchant": merchant, "category": category, "source": source},
        "document": f"merchant: {merchant}\ncategory: {category}\nsource: {source}",
        "embedding": embedding,
    }


_KB_DOCS = [
    _make_doc("kb1", "KFC", "Food", "kb", [1.0, 0.0, 0.0]),
    _make_doc("kb2", "Shell", "Fuel", "kb", [0.0, 1.0, 0.0]),
    _make_doc("kb3", "Uber", "Transport", "kb", [0.0, 0.0, 1.0]),
    _make_doc("kb4", "Pizza", "Food", "kb", [0.9, 0.1, 0.0]),
]


class TestEmbedder:
    def test_empty_text_rejected(self):
        with pytest.raises(ValueError):
            embedder.embed_text("")

    def test_whitespace_only_text_rejected(self):
        with pytest.raises(ValueError):
            embedder.embed_text("   ")

    def test_embed_text_returns_vector(self):
        with patch.object(embedder, "_get_model") as mock_model:
            mock_model.return_value.encode.return_value = np.array([0.1, 0.2, 0.3])
            result = embedder.embed_text("KFC")
        assert result == pytest.approx([0.1, 0.2, 0.3])


class TestRetriever:
    @pytest.mark.parametrize("query", ["", "   ", "\n\t"])
    def test_empty_query_returns_safely(self, query):
        with patch.object(retriever, "get_collection") as mock_collection:
            mock_collection.return_value.count.return_value = 5
            results = retriever.retrieve_similar_merchants(query)
        assert results == []
        mock_collection.return_value.query.assert_not_called()

    def test_empty_collection_returns_empty(self):
        collection = FakeCollection([])
        with patch.object(retriever, "get_collection", return_value=collection):
            results = retriever.retrieve_similar_merchants("KFC")
        assert results == []

    def test_returns_ranked_results(self):
        collection = FakeCollection(_KB_DOCS)
        with patch.object(retriever, "get_collection", return_value=collection):
            with patch.object(retriever, "embed_text", return_value=[1.0, 0.0, 0.0]):
                results = retriever.retrieve_similar_merchants("KFC")
        assert len(results) == 3
        assert results[0].matched_merchant == "KFC"
        assert results[0].category == "Food"
        confidences = [r.confidence for r in results]
        assert confidences == sorted(confidences, reverse=True)
        assert results[0].confidence > results[1].confidence

    def test_top_k_limits_results(self):
        collection = FakeCollection(_KB_DOCS)
        with patch.object(retriever, "get_collection", return_value=collection):
            with patch.object(retriever, "embed_text", return_value=[0.0, 1.0, 0.0]):
                results = retriever.retrieve_similar_merchants("Shell", top_k=2)
        assert len(results) == 2
        assert results[0].matched_merchant == "Shell"

    def test_default_top_k_used(self):
        collection = FakeCollection(_KB_DOCS)
        with patch.object(retriever, "get_collection", return_value=collection):
            with patch.object(retriever, "embed_text", return_value=[0.0, 0.0, 1.0]):
                results = retriever.retrieve_similar_merchants("Uber")
        assert len(results) == retriever.DEFAULT_TOP_K


class TestRagService:
    def _make_result(self, category, confidence, source="kb", merchant="KFC"):
        return RetrievalResult(
            category=category,
            confidence=confidence,
            source=source,
            matched_merchant=merchant,
            document_id="doc1",
        )

    def test_strong_rag_match(self):
        mock_db = MagicMock()
        with patch.object(
            rag_service,
            "retrieve_similar_merchants",
            return_value=[self._make_result("Food", 0.95)],
        ):
            result = rag_service.rag_categorize("KFC", mock_db)
        assert result["source"] == "rag"
        assert result["category"] == "Food"
        assert result["confidence"] >= rag_service.DEFAULT_THRESHOLD

    def test_weak_rag_context(self):
        mock_db = MagicMock()
        with patch.object(
            rag_service,
            "retrieve_similar_merchants",
            return_value=[
                self._make_result("Food", 0.45),
                self._make_result("Food", 0.40),
            ],
        ):
            result = rag_service.rag_categorize("KFC", mock_db)
        assert result["source"] == "rag_context"
        assert result["category"] is None
        assert result["confidence"] < rag_service.DEFAULT_THRESHOLD
        assert len(result["context"]) == 2

    def test_no_results_returns_none(self):
        mock_db = MagicMock()
        with patch.object(rag_service, "retrieve_similar_merchants", return_value=[]):
            assert rag_service.rag_categorize("KFC", mock_db) is None

    def test_retrieval_failure_returns_none(self):
        mock_db = MagicMock()
        with patch.object(
            rag_service,
            "retrieve_similar_merchants",
            side_effect=RuntimeError("chroma down"),
        ):
            assert rag_service.rag_categorize("KFC", mock_db) is None
