"""RAG categorization orchestration service.

Coordinates retrieval, similarity evaluation, and RAG result/context
preparation. This service does not make final categorization decisions
beyond the similarity threshold check; weak matches surface retrieved
context for the existing AI categorizer to use.
"""

import logging
import os
from typing import Optional

from dotenv import load_dotenv
from sqlmodel import Session

from app.schemas.rag import RAGCategorizeResult, RAGContextItem
from app.vector_db.retriever import retrieve_similar_merchants

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = int(os.environ.get("RAG_TOP_K", "3"))
DEFAULT_THRESHOLD = float(os.environ.get("RAG_SIMILARITY_THRESHOLD", "0.70"))


def rag_categorize(
    merchant_name: str,
    db: Session,  # noqa: ARG001  (retained for pipeline signature parity)
) -> Optional[dict]:
    """Attempt categorization using RAG retrieval.

    Flow:
      retrieval -> similarity evaluation -> RAG result/context preparation.

    Returns:
        None if no results are available (caller should use the AI
        categorizer) or if retrieval fails.
        A dict with `category` set when the best match meets the
        similarity threshold (source="rag").
        A dict with `category` None and `context` populated when the best
        match is below the threshold (source="rag_context").
    """
    try:
        results = retrieve_similar_merchants(
            query=merchant_name,
            top_k=DEFAULT_TOP_K,
        )
    except Exception as exc:  # Chroma, embedding, or retrieval failure
        logger.error(
            "RAG_retrieval merchant=%r outcome=failure error=%s",
            merchant_name,
            exc,
            exc_info=True,
        )
        return None

    if not results:
        logger.info(
            "RAG_retrieval merchant=%r outcome=no_results",
            merchant_name,
        )
        return None

    best = results[0]
    context = [
        RAGContextItem(
            merchant=item.matched_merchant,
            category=item.category,
            confidence=item.confidence,
            source=item.source,
        )
        for item in results
    ]

    if best.confidence >= DEFAULT_THRESHOLD:
        logger.info(
            "RAG_retrieval merchant=%r outcome=strong_match "
            "category=%s confidence=%.4f matched_merchant=%r source=%s "
            "results=%s",
            merchant_name,
            best.category,
            best.confidence,
            best.matched_merchant,
            best.source,
            [
                {
                    "merchant": item.matched_merchant,
                    "category": item.category,
                    "confidence": round(item.confidence, 4),
                    "source": item.source,
                }
                for item in results
            ],
        )
        return RAGCategorizeResult(
            category=best.category,
            confidence=best.confidence,
            source="rag",
            matched_merchant=best.matched_merchant,
            context=context,
        ).model_dump()

    logger.warning(
        "RAG_retrieval merchant=%r outcome=weak_match(rag_context) "
        "best_confidence=%.4f best_matched_merchant=%r results=%s "
        "decision_deferred_to_ai=True",
        merchant_name,
        best.confidence,
        best.matched_merchant,
        [
            {
                "merchant": item.matched_merchant,
                "category": item.category,
                "confidence": round(item.confidence, 4),
                "source": item.source,
            }
            for item in results
        ],
    )
    return RAGCategorizeResult(
        category=None,
        confidence=best.confidence,
        source="rag_context",
        matched_merchant=best.matched_merchant,
        context=context,
    ).model_dump()