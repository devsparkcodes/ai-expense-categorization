"""Retrieval logic for the RAG store.

Queries the vector collection for the nearest merchant records and
returns structured RetrievalResult objects. This module is responsible
only for: query -> embedding -> Chroma similarity search -> results.
No categorization decision is made here.
"""

import os
from typing import Optional

import numpy as np
from dotenv import load_dotenv

from app.schemas.rag import RetrievalResult
from app.vector_db.database import get_collection
from app.vector_db.embedder import embed_text

load_dotenv()

DEFAULT_TOP_K = int(os.environ.get("RAG_TOP_K", "3"))
DEFAULT_THRESHOLD = float(os.environ.get("RAG_SIMILARITY_THRESHOLD", "0.70"))


def _cosine_similarity(query_vector: list[float], candidate_vectors: list[list[float]]) -> list[float]:
    """Return cosine similarity between a query vector and candidate vectors.

    Chroma exposes raw distance (whose meaning depends on the configured
    collection space, e.g. l2). Computing cosine similarity directly from
    the retrieved embeddings avoids any space-specific interpretation.
    """
    query = np.asarray(query_vector, dtype=np.float32)
    query = query / (np.linalg.norm(query) + 1e-12)
    candidates = np.asarray(candidate_vectors, dtype=np.float32)
    candidates = candidates / (np.linalg.norm(candidates, axis=1, keepdims=True) + 1e-12)
    return (candidates @ query).tolist()


def retrieve_similar_merchants(
    query: str, top_k: Optional[int] = None
) -> list[RetrievalResult]:
    """Retrieve the top-K most similar merchant knowledge items.

    Args:
        query: the merchant text to embed and match.
        top_k: number of results to return; defaults to RAG_TOP_K.

    Returns:
        A list of RetrievalResult, ordered by descending similarity.
        Returns an empty list if the query is empty or the collection has
        no documents.
    """
    if not query or not query.strip():
        return []

    collection = get_collection()
    if collection.count() == 0:
        return []

    query_vector = embed_text(query)
    limit = top_k if top_k is not None else DEFAULT_TOP_K

    response = collection.query(
        query_embeddings=[query_vector],
        n_results=limit,
        include=["metadatas", "documents", "embeddings"],
    )

    ids = response["ids"][0]
    metadatas = response["metadatas"][0] or []
    embeddings = response["embeddings"][0]

    scores = _cosine_similarity(query_vector, embeddings) if embeddings is not None and len(embeddings) > 0 else []

    results = []
    for index, doc_id in enumerate(ids):
        metadata = metadatas[index] if index < len(metadatas) else {}
        results.append(
            RetrievalResult(
                category=metadata.get("category", ""),
                confidence=float(scores[index]),
                source=metadata.get("source", ""),
                matched_merchant=metadata.get("merchant", ""),
                document_id=doc_id,
            )
        )

    results.sort(key=lambda result: result.confidence, reverse=True)
    return results