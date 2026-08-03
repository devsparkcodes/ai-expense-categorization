from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Transaction(SQLModel, table=True):
    """Represents a financial transaction."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    merchant_name: str
    amount: Decimal
    currency: str  # ISO 4217 currency code (e.g. PKR, USD)
    description: Optional[str] = None
    transaction_date: datetime
    predicted_category: str
    confidence: float = Field(default=1.0)
    prediction_source: str = Field(default="rule_engine")
    requires_review: bool = Field(default=False)
    is_verified: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
