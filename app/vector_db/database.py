"""Chroma client and collection management.

Responsible for the Chroma persistent client and the RAG collection handle.
"""

import os
from pathlib import Path

import chromadb
from chromadb import Collection
from dotenv import load_dotenv

load_dotenv()

_COLLECTION_NAME = os.environ.get("RAG_COLLECTION_NAME", "merchant_knowledge")


def _resolve_store_dir() -> Path:
    """Return the configured directory where Chroma persists its data."""
    configured = os.environ.get("VECTOR_STORE_DIR")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parent.parent.parent / "data" / "vector_store"


def get_collection() -> Collection:
    """Create or load the persistent Chroma collection and return it.

    The client and collection are created once and cached on the module,
    so repeated calls reuse the same live handles.
    """
    store_dir = _resolve_store_dir()
    store_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(store_dir))
    return client.get_or_create_collection(name=_COLLECTION_NAME)