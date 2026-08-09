"""CLI to build/refresh the RAG vector index.

Usage:
    python scripts/build_vector_index.py

or, from anywhere on the package path:
    python -m scripts.build_vector_index

Loads the project environment (.env), opens a database session with the
existing database setup, delegates all indexing to
``app.vector_db.indexer.build_vector_index`` (idempotent, upserts in
place), then closes the session safely. Exits non-zero on failure.
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.database.database import engine  # noqa: E402
from app.vector_db.database import get_collection  # noqa: E402
from app.vector_db.indexer import build_vector_index  # noqa: E402


def main() -> int:
    load_dotenv(_PROJECT_ROOT / ".env")

    try:
        with Session(engine) as session:
            build_vector_index(session)
            count = get_collection().count()
    except Exception as exc:
        print(f"Failed to build vector index: {exc}", file=sys.stderr)
        return 1

    print(f"Vector index built successfully. Collection contains {count} documents.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
