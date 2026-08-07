from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class TransactionCreate(BaseModel):
    """Schema for creating a new transaction."""

    merchant_name: str
    amount: Decimal
    currency: str
    description: Optional[str] = None
    transaction_date: datetime


class TransactionBatchResult(BaseModel):
    """Schema for a single batch transaction processing result."""

    success: bool
    transaction_id: Optional[UUID] = None
    merchant_name: str
    predicted_category: Optional[str] = None
    error: Optional[str] = None
