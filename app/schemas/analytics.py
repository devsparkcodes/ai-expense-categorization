from pydantic import BaseModel


class AnalyticsSummaryResponse(BaseModel):
    """Schema for the analytics summary response."""

    total_transactions: int
    total_spending: float
    average_transaction: float
    highest_transaction: float


class CategoryBreakdownItem(BaseModel):
    """Schema for a single category breakdown entry."""

    category: str
    total_spending: float
    transaction_count: int


class TopMerchantItem(BaseModel):
    """Schema for a single top merchant entry."""

    merchant: str
    total_spending: float
    transaction_count: int
