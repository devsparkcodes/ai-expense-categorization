"""Index maintenance for the vector store.

Builds/refreshes the collection from known data sources:
- app/data/merchant_categories.json
- CategoryFeedback
- verified transactions

The indexer is idempotent: every document is upserted under a stable,
source-derived id so re-running it updates in place instead of duplicating.
"""

import json
import re
from pathlib import Path
from uuid import UUID

from sqlmodel import Session, select

from app.models.category_feedback import CategoryFeedback
from app.models.transaction import Transaction
from app.vector_db.database import get_collection
from app.vector_db.embedder import embed_text

_KB_PATH = Path(__file__).resolve().parent.parent / "data" / "merchant_categories.json"


def _stable_merchant_id(merchant_name: str) -> str:
    """Return a stable, slug-like identifier for a merchant name."""
    slug = re.sub(r"[^a-z0-9]+", "-", merchant_name.lower()).strip("-")
    return slug or "unknown"


def _build_document(
    merchant: str,
    category: str,
    source: str,
    aliases: str = "",
    keywords: str = "",
) -> str:
    """Render a knowledge item as a structured document for embedding."""
    return (
        f"merchant: {merchant}\n"
        f"aliases: {aliases}\n"
        f"category: {category}\n"
        f"keywords: {keywords}\n"
        f"source: {source}"
    )


def _kb_entries() -> list[dict]:
    """Yield merchant knowledge base entries as raw structured records."""
    with open(_KB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    entries = []
    for category, merchants in data.items():
        for merchant in merchants:
            entries.append(
                {
                    "id": f"kb|{_stable_merchant_id(merchant)}",
                    "merchant": merchant,
                    "aliases": "",
                    "category": category,
                    "keywords": "",
                    "source": "kb",
                }
            )
    return entries


def _feedback_entries(db: Session) -> list[dict]:
    """Yield CategoryFeedback records as raw structured records."""
    records = db.exec(select(CategoryFeedback)).all()
    entries = []
    for feedback in records:
        entries.append(
            {
                "id": f"feedback|{feedback.id}",
                "merchant": feedback.merchant_name,
                "aliases": "",
                "category": feedback.corrected_category,
                "keywords": "",
                "source": "feedback",
            }
        )
    return entries


def _verified_transaction_entries(db: Session) -> list[dict]:
    """Yield verified transactions as raw structured records."""
    records = db.exec(
        select(Transaction).where(Transaction.is_verified == True)  # noqa: E712
    ).all()
    entries = []
    for transaction in records:
        entries.append(
            {
                "id": f"verified|{transaction.id}",
                "merchant": transaction.merchant_name,
                "aliases": "",
                "category": transaction.predicted_category,
                "keywords": "",
                "source": "verified",
            }
        )
    return entries


def build_vector_index(db: Session) -> None:
    """Build or refresh the Chroma knowledge base from all data sources.

    Reads the merchant KB, the CategoryFeedback table, and verified
    transactions, then upserts each item (embedded) into Chroma under a
    stable id. Running this multiple times is safe: existing ids are
    updated, never duplicated.

    Args:
        db: an active SQLModel session used to read database sources.
    """
    entries = _kb_entries() + _feedback_entries(db) + _verified_transaction_entries(db)

    ids = [entry["id"] for entry in entries]
    documents = [
        _build_document(
            merchant=entry["merchant"],
            category=entry["category"],
            source=entry["source"],
            aliases=entry["aliases"],
            keywords=entry["keywords"],
        )
        for entry in entries
    ]
    embeddings = [embed_text(doc) for doc in documents]
    metadatas = [
        {
            "merchant": entry["merchant"],
            "category": entry["category"],
            "source": entry["source"],
        }
        for entry in entries
    ]

    collection = get_collection()
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )