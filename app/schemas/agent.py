"""Schemas for the OpenAI Agents SDK orchestration layer."""

from typing import Literal

from pydantic import BaseModel


class CategorizeOutcome(BaseModel):
    """Structured final output of the categorization agent."""

    category: str
    confidence: float
    prediction_source: Literal["rule_engine", "rag", "ai", "uncategorized"]
    requires_review: bool