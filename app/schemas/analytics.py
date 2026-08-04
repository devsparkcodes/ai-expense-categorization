from pydantic import BaseModel


class AnalyticsSummaryResponse(BaseModel):
    """Schema for the analytics summary response."""

    total_transactions: int
    total_spending: float
    average_transaction: float
    highest_transaction: float
