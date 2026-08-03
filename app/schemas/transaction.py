from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class TransactionCreate(BaseModel):
    """Schema for creating a new transaction."""

    merchant_name: str
    amount: Decimal
    currency: str
    description: Optional[str] = None
    transaction_date: datetime
