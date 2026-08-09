"""Pytest tests for the Phase 9 transaction-service agent integration.

No live LLM/API calls: the agent entry point and supporting services are
mocked so only create_transaction / batch behavior is exercised.

Run with:  .venv\\Scripts\\python.exe -m pytest tests/test_transaction_agent.py -v
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.schemas.agent import CategorizeOutcome
from app.schemas.transaction import TransactionCreate
import app.services.transaction as tx


def make_data(merchant):
    return TransactionCreate(
        merchant_name=merchant,
        amount=Decimal("25.00"),
        currency="USD",
        transaction_date=datetime.now(),
    )


def outcome(category, confidence, source, review):
    return CategorizeOutcome(
        category=category,
        confidence=confidence,
        prediction_source=source,
        requires_review=review,
    )


def test_rule_match(db):
    """Rule/feedback match surfaced through the agent outcome."""
    with patch.object(
        tx, "run_categorization", return_value=outcome("Food", 1.0, "rule_engine", False)
    ):
        result = tx.create_transaction(db, make_data("ALDI"))
    assert result["predicted_category"] == "Food"
    assert result["prediction_source"] == "rule_engine"
    assert result["requires_review"] is False
    assert result["confidence"] == 1.0
    assert result["is_verified"] is False


def test_strong_rag(db):
    """Strong RAG match is preserved through the agent outcome."""
    with patch.object(
        tx, "run_categorization", return_value=outcome("Fuel", 0.87, "rag", False)
    ):
        result = tx.create_transaction(db, make_data("CALTEX"))
    assert result["predicted_category"] == "Fuel"
    assert result["prediction_source"] == "rag"
    assert result["confidence"] == 0.87
    assert result["requires_review"] is False


def test_weak_rag_to_ai(db):
    """Weak RAG + AI resolution carries the AI review flag."""
    with patch.object(
        tx, "run_categorization", return_value=outcome("Transport", 0.5, "ai", True)
    ):
        result = tx.create_transaction(db, make_data("UBER"))
    assert result["predicted_category"] == "Transport"
    assert result["prediction_source"] == "ai"
    assert result["requires_review"] is True


def test_rag_failure_to_ai(db):
    """RAG retrieval failure still surfaces an AI outcome from the agent."""
    with patch.object(
        tx, "run_categorization", return_value=outcome("Healthcare", 0.5, "ai", True)
    ):
        result = tx.create_transaction(db, make_data("PHARMACY"))
    assert result["predicted_category"] == "Healthcare"
    assert result["prediction_source"] == "ai"


def test_agent_failure_legacy_rule(db):
    """Agent failure falls back to the synchronous feedback/rule path."""
    with patch.object(tx, "run_categorization", side_effect=RuntimeError("agent boom")):
        with patch.object(tx, "predict_category", return_value="Education"):
            result = tx.create_transaction(db, make_data("KIPS SCHOOL"))
    assert result["predicted_category"] == "Education"
    assert result["prediction_source"] == "rule_engine"
    assert result["confidence"] == 1.0


def test_agent_failure_legacy_full_pipeline(db):
    """Agent failure: full legacy pipeline Feedback -> Rule -> RAG -> AI."""
    with patch.object(tx, "run_categorization", side_effect=RuntimeError("agent boom")):
        with patch.object(tx, "predict_category", return_value="Uncategorized"):
            with patch.object(tx, "rag_categorize", return_value=None):
                with patch.object(tx, "predict_category_ai", return_value="Other"):
                    result = tx.create_transaction(db, make_data("RANDOM SHOP"))
    assert result["predicted_category"] == "Other"
    assert result["prediction_source"] == "ai"
    assert result["requires_review"] is True


def test_batch_success(db):
    """Batch processing handles each transaction independently through the agent."""
    with patch.object(
        tx,
        "run_categorization",
        side_effect=[
            outcome("Food", 1.0, "rule_engine", False),
            outcome("Shopping", 0.5, "ai", True),
        ],
    ):
        results = tx.create_transactions_batch(
            db, [make_data("MCDONALDS"), make_data("ASOS")]
        )
    assert len(results) == 2
    assert all(item["success"] for item in results)
    assert [item["predicted_category"] for item in results] == ["Food", "Shopping"]


def test_batch_independence(db):
    """A per-row failure does not stop the remaining rows."""
    with patch.object(
        tx,
        "run_categorization",
        side_effect=[outcome("Food", 1.0, "rule_engine", False), RuntimeError("bad merchant")],
    ):
        with patch.object(tx, "_categorize_sync", side_effect=RuntimeError("sync failure")):
            results = tx.create_transactions_batch(db, [make_data("MCD"), make_data("X")])
    assert results[0]["success"] is True
    assert results[1]["success"] is False


def test_fail_guard(db):
    """The intentional test error ('FAIL' merchant) is preserved."""
    with pytest.raises(Exception) as exc_info:
        tx.create_transaction(db, make_data("FAIL"))
    assert str(exc_info.value) == "Intentional test error"