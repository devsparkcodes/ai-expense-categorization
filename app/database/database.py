from typing import Generator

from sqlmodel import SQLModel, Session, create_engine

SQL_DATABASE_URL = "sqlite:///./expense.db"

engine = create_engine(SQL_DATABASE_URL, echo=False)


def get_session() -> Generator[Session, None, None]:
    """Yield a reusable database session."""
    with Session(engine) as session:
        yield session


def create_db_and_tables() -> None:
    """Create all database tables."""
    SQLModel.metadata.create_all(engine)
