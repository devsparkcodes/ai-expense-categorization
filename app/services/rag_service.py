"""RAG categorization orchestration service.

Coordinates embedding, retrieval, and AI fallback to produce a category.
Kept as a thin, single-responsibility layer for future Agent SDK tooling.
"""

# TODO: implement rag_categorize(merchant_name, db)