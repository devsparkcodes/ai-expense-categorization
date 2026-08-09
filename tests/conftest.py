"""Shared pytest fixtures for the AI Expense Categorization test suite.

Isolation guarantees:
- Tests use an in-memory SQLite database (never the project's expense.db).
- No Chroma vector store is created or touched here.
- No LLM/OpenRouter calls are made from fixtures.

The in-memory engine uses a StaticPool so that all sessions created by the
`db` fixture share the same underlying in-memory database.
"""

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.models.category_feedback import CategoryFeedback  # noqa: F401  (register tables)
from app.models.transaction import Transaction  # noqa: F401  (register tables)


@pytest.fixture(scope="session")
def engine():
    """A session-scoped in-memory SQLite engine with all tables created."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture()
def db(engine):
    """Provide a fresh SQLModel session bound to the in-memory database."""
    with Session(engine) as session:
        yield session