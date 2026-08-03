from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class CategoryFeedback(SQLModel, table=True):
    """Stores manual category corrections for future AI learning."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    merchant_name: str
    original_category: str
    corrected_category: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
