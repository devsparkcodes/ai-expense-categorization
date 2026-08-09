"""Unit tests for the analytics service functions.

Tests the exact behavior implemented in app/services/analytics.py:
- get_summary: total count / spending / average / highest (no filters)
- get_category_breakdown: grouped by predicted_category, desc by spend
- get_top_merchants: grouped by merchant, desc by spend, top 10
- get_daily_spending / get_weekly_spending / get_monthly_spending: SQLite
  strftime grouping

No LLM/OpenRouter calls. Uses the conftest.py `db` fixture (in-memory).
Each test starts from an empty transaction table for determinism.
"""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete
from sqlmodel import Session

from app.models.transaction import Transaction
from app.services import analytics


def _add(db: Session, merchant, amount, category, date, *, verified=True, source="rule_engine", confidence=1.0):
    """Add a single transaction and commit."""
    tx = Transaction(
        merchant_name=merchant,
        amount=Decimal(str(amount)),
        currency="PKR",
        transaction_date=date,
        predicted_category=category,
        prediction_source=source,
        confidence=confidence,
        requires_review=source == "ai",
        is_verified=verified,
    )
    db.add(tx)
    db.commit()


@pytest.fixture(autouse=True)
def _clean_transactions(db):
    """Each test starts with an empty transaction table."""
    db.exec(delete(Transaction))
    db.commit()
    yield


class TestGetSummary:
    def test_empty_database_returns_zeroed_summary(self, db):
        summary = analytics.get_summary(db)
        assert summary == {
            "total_transactions": 0,
            "total_spending": 0.0,
            "average_transaction": 0.0,
            "highest_transaction": 0.0,
        }

    def test_total_transaction_count(self, db):
        _add(db, "KFC", 100.0, "Food", datetime(2024, 1, 5))
        _add(db, "Shell", 50.0, "Fuel", datetime(2024, 1, 6))
        _add(db, "Netflix", 30.0, "Entertainment", datetime(2024, 1, 7))
        summary = analytics.get_summary(db)
        assert summary["total_transactions"] == 3

    def test_total_spending(self, db):
        _add(db, "KFC", 100.50, "Food", datetime(2024, 1, 5))
        _add(db, "Shell", 50.25, "Fuel", datetime(2024, 1, 6))
        _add(db, "Netflix", 30.00, "Entertainment", datetime(2024, 1, 7))
        summary = analytics.get_summary(db)
        assert summary["total_spending"] == 180.75

    def test_average_and_highest(self, db):
        _add(db, "KFC", 100.0, "Food", datetime(2024, 1, 5))
        _add(db, "Shell", 50.0, "Fuel", datetime(2024, 1, 6))
        _add(db, "Netflix", 300.0, "Entertainment", datetime(2024, 1, 7))
        summary = analytics.get_summary(db)
        assert summary["average_transaction"] == 150.0
        assert summary["highest_transaction"] == 300.0

    def test_unverified_transactions_are_included(self, db):
        """The implementation does not filter on is_verified -- verify that."""
        _add(db, "KFC", 100.0, "Food", datetime(2024, 1, 5), verified=False)
        _add(db, "Shell", 50.0, "Fuel", datetime(2024, 1, 6), verified=True)
        summary = analytics.get_summary(db)
        assert summary["total_transactions"] == 2
        assert summary["total_spending"] == 150.0

    def test_ai_source_transactions_are_included(self, db):
        _add(db, "KFC", 100.0, "Food", datetime(2024, 1, 5), source="ai", confidence=0.5)
        summary = analytics.get_summary(db)
        assert summary["total_transactions"] == 1
        assert summary["total_spending"] == 100.0


class TestGetCategoryBreakdown:
    def test_empty_database_returns_empty_list(self, db):
        assert analytics.get_category_breakdown(db) == []

    def test_groups_by_category_with_spending_and_count(self, db):
        _add(db, "KFC", 100.0, "Food", datetime(2024, 1, 5))
        _add(db, "Burger King", 60.0, "Food", datetime(2024, 1, 6))
        _add(db, "Shell", 50.0, "Fuel", datetime(2024, 1, 7))
        rows = analytics.get_category_breakdown(db)
        assert rows == [
            {"category": "Food", "total_spending": 160.0, "transaction_count": 2},
            {"category": "Fuel", "total_spending": 50.0, "transaction_count": 1},
        ]

    def test_orders_by_spending_desc_not_insertion(self, db):
        _add(db, "Fuel", 50.0, "CategoryFuel", datetime(2024, 1, 5))
        _add(db, "Food", 10.0, "CategoryFood", datetime(2024, 1, 6))
        _add(db, "Other", 200.0, "CategoryOther", datetime(2024, 1, 7))
        rows = analytics.get_category_breakdown(db)
        assert [r["category"] for r in rows] == ["CategoryOther", "CategoryFuel", "CategoryFood"]


class TestGetTopMerchants:
    def test_empty_database_returns_empty_list(self, db):
        assert analytics.get_top_merchants(db) == []

    def test_groups_by_merchant_and_sorts_by_spend(self, db):
        _add(db, "KFC", 100.0, "Food", datetime(2024, 1, 5))
        _add(db, "KFC", 50.0, "Food", datetime(2024, 1, 6))
        _add(db, "Shell", 200.0, "Fuel", datetime(2024, 1, 7))
        rows = analytics.get_top_merchants(db)
        assert rows == [
            {"merchant": "Shell", "total_spending": 200.0, "transaction_count": 1},
            {"merchant": "KFC", "total_spending": 150.0, "transaction_count": 2},
        ]

    def test_limits_to_ten_merchants(self, db):
        for i in range(12):
            _add(db, f"Merchant{i}", float(i + 1), "Food", datetime(2024, 1, 5))
        rows = analytics.get_top_merchants(db)
        assert len(rows) == 10
        assert rows[0]["merchant"] == "Merchant11"
        assert rows[9]["merchant"] == "Merchant2"


class TestGetDailySpending:
    def test_empty_database_returns_empty_list(self, db):
        assert analytics.get_daily_spending(db) == []

    def test_grouped_by_day(self, db):
        _add(db, "KFC", 100.0, "Food", datetime(2024, 1, 5, 9, 0))
        _add(db, "KFC", 50.0, "Food", datetime(2024, 1, 5, 20, 0))
        _add(db, "Shell", 200.0, "Fuel", datetime(2024, 1, 7, 12, 0))
        rows = analytics.get_daily_spending(db)
        assert rows == [
            {"period": "2024-01-05", "total_spending": 150.0},
            {"period": "2024-01-07", "total_spending": 200.0},
        ]

    def test_sorted_ascending_by_period(self, db):
        _add(db, "Later", 10.0, "Other", datetime(2024, 2, 1))
        _add(db, "Earlier", 20.0, "Other", datetime(2023, 12, 31))
        rows = analytics.get_daily_spending(db)
        assert [r["period"] for r in rows] == ["2023-12-31", "2024-02-01"]


class TestGetWeeklySpending:
    def test_empty_database_returns_empty_list(self, db):
        assert analytics.get_weekly_spending(db) == []

    def test_grouped_by_iso_week(self, db):
        # 2024-01-08 (Monday) and 2024-01-12 (Friday) are the same ISO week; 2024-01-01 is week 01.
        _add(db, "A", 100.0, "Food", datetime(2024, 1, 8))
        _add(db, "B", 50.0, "Food", datetime(2024, 1, 12))
        _add(db, "C", 200.0, "Fuel", datetime(2024, 1, 1))
        rows = analytics.get_weekly_spending(db)
        assert rows == [
            {"period": "2024-W01", "total_spending": 200.0},
            {"period": "2024-W02", "total_spending": 150.0},
        ]

    def test_cross_year_weeks_use_iso_year(self, db):
        # 2023-01-01 (a Sunday) belongs to ISO year 2022, week 52.
        _add(db, "A", 100.0, "Food", datetime(2024, 1, 1))
        _add(db, "B", 50.0, "Food", datetime(2023, 1, 1))
        rows = analytics.get_weekly_spending(db)
        assert [r["period"] for r in rows] == ["2022-W52", "2024-W01"]


class TestGetMonthlySpending:
    def test_empty_database_returns_empty_list(self, db):
        assert analytics.get_monthly_spending(db) == []

    def test_grouped_by_month(self, db):
        _add(db, "A", 100.0, "Food", datetime(2024, 1, 5))
        _add(db, "B", 50.0, "Food", datetime(2024, 1, 25))
        _add(db, "C", 200.0, "Fuel", datetime(2024, 2, 2))
        rows = analytics.get_monthly_spending(db)
        assert rows == [
            {"period": "2024-01", "total_spending": 150.0},
            {"period": "2024-02", "total_spending": 200.0},
        ]

    def test_sorted_ascending_by_period(self, db):
        _add(db, "A", 10.0, "Other", datetime(2024, 12, 1))
        _add(db, "B", 20.0, "Other", datetime(2024, 1, 1))
        rows = analytics.get_monthly_spending(db)
        assert [r["period"] for r in rows] == ["2024-01", "2024-12"]