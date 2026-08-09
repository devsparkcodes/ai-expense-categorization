"""API-level tests for the FastAPI application (transaction + analytics routers).

- Uses FastAPI TestClient with the conftest `engine` (in-memory SQLite, StaticPool).
- Overrides the `get_session` dependency so no request ever touches expense.db.
- The categorization agent (real OpenRouter/LLM) is mocked via
  `app.services.transaction.run_categorization` -> a structured CategorizeOutcome.
- The persistent Chroma vector store is never used.

Only endpoints that actually exist in app/api are tested:
  GET/POST /transactions/, GET/PUT/DELETE /transactions/{id},
  PATCH /transactions/{id}/category, POST /transactions/batch,
  GET /analytics/{summary,category-breakdown,top-merchants,daily-spending,
  weekly-spending,monthly-spending}.

There is NO /rag or /agents router in the codebase.
"""

from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlmodel import Session

from app.main import app
from app.database.database import get_session
from app.models.category_feedback import CategoryFeedback
from app.models.transaction import Transaction
from app.schemas.agent import CategorizeOutcome

CATEGORY_MAP = {
    "KFC": "Food",
    "Burger King": "Food",
    "Shell": "Fuel",
    "Netflix": "Entertainment",
    "Uber": "Transport",
}


def _categorize(merchant_name, db):
    return CategorizeOutcome(
        category=CATEGORY_MAP.get(merchant_name, "Uncategorized"),
        confidence=1.0,
        prediction_source="rule_engine",
        requires_review=False,
    )


def _payload(merchant="KFC", amount=100.0, date=datetime(2024, 1, 5, 10, 30)):
    return {
        "merchant_name": merchant,
        "amount": amount,
        "currency": "PKR",
        "description": f"lunch at {merchant}",
        "transaction_date": date.isoformat(),
    }


@pytest.fixture()
def client(engine):
    """TestClient whose DB dependency is bound to the in-memory engine."""
    from app.main import app as _app
    from app.database.database import get_session as _get_session

    def override_get_session():
        with Session(engine) as session:
            yield session

    _app.dependency_overrides[_get_session] = override_get_session
    test_client = TestClient(_app)
    yield test_client
    _app.dependency_overrides.pop(_get_session, None)


@pytest.fixture(autouse=True)
def _clean_db(engine):
    """Empty all tables before each test so the shared DB stays deterministic."""
    with Session(engine) as session:
        session.exec(delete(CategoryFeedback))
        session.exec(delete(Transaction))
        session.commit()
    yield


def _create(client, merchant="KFC", amount=100.0, date=datetime(2024, 1, 5, 10, 30)):
    import unittest.mock as mock

    with mock.patch("app.services.transaction.run_categorization", side_effect=_categorize):
        resp = client.post("/transactions/", json=_payload(merchant, amount, date))
    assert resp.status_code == 201
    return resp.json()


class TestCreateTransaction:
    def test_creates_transaction_with_categorized_fields(self, client):
        data = _create(client, "KFC", 100.0)
        assert data["merchant_name"] == "KFC"
        assert data["amount"] == 100
        assert data["predicted_category"] == "Food"
        assert data["prediction_source"] == "rule_engine"
        assert data["confidence"] == 1.0
        assert data["requires_review"] is False
        assert data["is_verified"] is False

    def test_unknown_merchant_gets_uncategorized_rule_outcome(self, client):
        data = _create(client, "SomeObscureShop", 10.0)
        assert data["predicted_category"] == "Uncategorized"

    def test_validation_error_for_missing_fields(self, client):
        resp = client.post("/transactions/", json={"currency": "PKR"})
        assert resp.status_code == 422


class TestListTransactions:
    def test_empty_list(self, client):
        resp = client.get("/transactions/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_all_created_transactions(self, client):
        _create(client, "KFC", 100.0, datetime(2024, 1, 5))
        _create(client, "Shell", 50.0, datetime(2024, 1, 1))
        _create(client, "Netflix", 30.0, datetime(2024, 1, 3))
        resp = client.get("/transactions/")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 3
        assert {r["merchant_name"] for r in rows} == {"KFC", "Shell", "Netflix"}

    def test_default_sort_is_date_desc(self, client):
        _create(client, "Old", 10.0, datetime(2023, 1, 1))
        _create(client, "New", 20.0, datetime(2024, 6, 1))
        rows = client.get("/transactions/").json()
        assert rows[0]["merchant_name"] == "New"

    def test_sort_by_amount_asc(self, client):
        _create(client, "A", 100.0)
        _create(client, "B", 10.0)
        rows = client.get("/transactions/", params={"sort_by": "amount", "order": "asc"}).json()
        assert [r["merchant_name"] for r in rows] == ["B", "A"]

    def test_invalid_sort_by_returns_400(self, client):
        resp = client.get("/transactions/", params={"sort_by": "bogus"})
        assert resp.status_code == 400

    def test_invalid_order_returns_400(self, client):
        resp = client.get("/transactions/", params={"order": "sideways"})
        assert resp.status_code == 400

    def test_invalid_page_returns_400(self, client):
        resp = client.get("/transactions/", params={"page": 0})
        assert resp.status_code == 400

    def test_invalid_limit_returns_400(self, client):
        resp = client.get("/transactions/", params={"limit": 0})
        assert resp.status_code == 400

    def test_pagination(self, client):
        for i in range(5):
            _create(client, f"Shop{i}", float(i + 1), datetime(2024, 1, i + 1))
        page1 = client.get("/transactions/", params={"page": 1, "limit": 2}).json()
        page3 = client.get("/transactions/", params={"page": 3, "limit": 2}).json()
        assert len(page1) == 2
        assert len(page3) == 1

    def test_category_filter(self, client):
        _create(client, "KFC", 100.0)
        _create(client, "Shell", 50.0)
        rows = client.get("/transactions/", params={"category": "food"}).json()
        assert len(rows) == 1
        assert rows[0]["merchant_name"] == "KFC"

    def test_merchant_filter_is_case_insensitive_substring(self, client):
        _create(client, "KFC Express", 100.0)
        _create(client, "Shell", 50.0)
        rows = client.get("/transactions/", params={"merchant": "kfc"}).json()
        assert [r["merchant_name"] for r in rows] == ["KFC Express"]

    def test_search_matches_description(self, client):
        import unittest.mock as mock

        def _categorize_other(merchant_name, db):
            return CategorizeOutcome(
                category="Other",
                confidence=1.0,
                prediction_source="rule_engine",
                requires_review=False,
            )

        with mock.patch("app.services.transaction.run_categorization", side_effect=_categorize_other):
            client.post(
                "/transactions/",
                json={
                    "merchant_name": "KFC",
                    "amount": 100.0,
                    "currency": "PKR",
                    "description": "family dinner",
                    "transaction_date": "2024-01-05T10:30:00",
                },
            )
            client.post(
                "/transactions/",
                json={
                    "merchant_name": "Shell",
                    "amount": 50.0,
                    "currency": "PKR",
                    "description": "fuel refill",
                    "transaction_date": "2024-01-06T10:30:00",
                },
            )
        rows = client.get("/transactions/", params={"search": "family"}).json()
        assert [r["merchant_name"] for r in rows] == ["KFC"]

    def test_date_range_filter(self, client):
        _create(client, "Jan", 10.0, datetime(2024, 1, 10))
        _create(client, "Feb", 20.0, datetime(2024, 2, 10))
        rows = client.get(
            "/transactions/",
            params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
        ).json()
        assert [r["merchant_name"] for r in rows] == ["Jan"]


class TestGetSingleTransaction:
    def test_returns_transaction_by_id(self, client):
        created = _create(client, "KFC", 100.0)
        resp = client.get(f"/transactions/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["merchant_name"] == "KFC"

    def test_unknown_id_returns_404(self, client):
        resp = client.get(f"/transactions/{uuid4()}")
        assert resp.status_code == 404


class TestUpdateTransaction:
    def test_updates_fields(self, client):
        created = _create(client, "KFC", 100.0)
        updated = _payload("Shell", 250.0, datetime(2024, 3, 1, 8, 0))
        resp = client.put(f"/transactions/{created['id']}", json=updated)
        assert resp.status_code == 200
        body = resp.json()
        assert body["merchant_name"] == "Shell"
        assert body["amount"] == 250
        assert body["transaction_date"].startswith("2024-03-01")
        assert body["predicted_category"] == "Food"  # update does not re-categorize

    def test_update_missing_returns_404(self, client):
        resp = client.put(
            f"/transactions/{uuid4()}",
            json=_payload("Shell", 10.0),
        )
        assert resp.status_code == 404


class TestDeleteTransaction:
    def test_deletes_then_404(self, client):
        created = _create(client, "KFC", 100.0)
        resp = client.delete(f"/transactions/{created['id']}")
        assert resp.status_code == 200
        assert resp.json() == {"message": "Transaction deleted successfully."}
        assert client.get(f"/transactions/{created['id']}").status_code == 404

    def test_missing_returns_404(self, client):
        resp = client.delete(f"/transactions/{uuid4()}")
        assert resp.status_code == 404


class TestUpdateTransactionCategory:
    def test_updates_category_and_records_feedback(self, client):
        created = _create(client, "KFC", 100.0)
        resp = client.patch(
            f"/transactions/{created['id']}/category", json={"category": "FastFood"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["predicted_category"] == "FastFood"
        assert body["is_verified"] is True
        assert body["requires_review"] is False
        assert body["prediction_source"] == "manual"

    def test_missing_transaction_returns_404(self, client):
        resp = client.patch(
            f"/transactions/{uuid4()}/category", json={"category": "Food"}
        )
        assert resp.status_code == 404


class TestBatchCreate:
    def test_batch_creates_multiple_and_reports(self, client):
        import unittest.mock as mock

        with mock.patch("app.services.transaction.run_categorization", side_effect=_categorize):
            resp = client.post(
                "/transactions/batch",
                json=[_payload("KFC", 100.0), _payload("Shell", 50.0)],
            )
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 2
        assert all(r["success"] is True for r in rows)
        assert [r["merchant_name"] for r in rows] == ["KFC", "Shell"]

    def test_fail_merchant_is_reported_without_aborting_batch(self, client):
        import unittest.mock as mock

        with mock.patch("app.services.transaction.run_categorization", side_effect=_categorize):
            resp = client.post(
                "/transactions/batch",
                json=[_payload("FAIL", 100.0), _payload("KFC", 200.0)],
            )
        rows = resp.json()
        assert rows[0]["success"] is False
        assert rows[0]["error"] == "Intentional test error"
        assert rows[1]["success"] is True


class TestAnalyticsSummary:
    def test_empty_database(self, client):
        resp = client.get("/analytics/summary")
        assert resp.status_code == 200
        assert resp.json() == {
            "total_transactions": 0,
            "total_spending": 0.0,
            "average_transaction": 0.0,
            "highest_transaction": 0.0,
        }

    def test_summary_after_creating_transactions(self, client):
        _create(client, "KFC", 100.0, datetime(2024, 1, 5))
        _create(client, "Shell", 50.0, datetime(2024, 1, 6))
        _create(client, "Netflix", 300.0, datetime(2024, 1, 7))
        resp = client.get("/analytics/summary")
        assert resp.status_code == 200
        assert resp.json()["total_transactions"] == 3
        assert resp.json()["total_spending"] == 450.0
        assert resp.json()["average_transaction"] == 150.0
        assert resp.json()["highest_transaction"] == 300.0


class TestAnalyticsCategoryBreakdown:
    def test_empty(self, client):
        resp = client.get("/analytics/category-breakdown")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_grouped_by_category(self, client):
        _create(client, "KFC", 100.0)
        _create(client, "Burger King", 60.0)
        _create(client, "Shell", 50.0)
        rows = client.get("/analytics/category-breakdown").json()
        assert rows == [
            {"category": "Food", "total_spending": 160.0, "transaction_count": 2},
            {"category": "Fuel", "total_spending": 50.0, "transaction_count": 1},
        ]


class TestAnalyticsTopMerchants:
    def test_empty(self, client):
        resp = client.get("/analytics/top-merchants")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_top_merchants_sorted(self, client):
        _create(client, "KFC", 100.0)
        _create(client, "KFC", 50.0)
        _create(client, "Shell", 200.0)
        rows = client.get("/analytics/top-merchants").json()
        assert rows == [
            {"merchant": "Shell", "total_spending": 200.0, "transaction_count": 1},
            {"merchant": "KFC", "total_spending": 150.0, "transaction_count": 2},
        ]


class TestAnalyticsSpending:
    def test_daily_spending_groups_and_sorts(self, client):
        _create(client, "KFC", 100.0, datetime(2024, 1, 5, 9))
        _create(client, "KFC", 50.0, datetime(2024, 1, 5, 20))
        _create(client, "Shell", 200.0, datetime(2024, 1, 7, 12))
        rows = client.get("/analytics/daily-spending").json()
        assert rows == [
            {"period": "2024-01-05", "total_spending": 150.0},
            {"period": "2024-01-07", "total_spending": 200.0},
        ]

    def test_weekly_spending_iso_weeks(self, client):
        _create(client, "A", 100.0, datetime(2024, 1, 8))
        _create(client, "B", 50.0, datetime(2024, 1, 12))
        rows = client.get("/analytics/weekly-spending").json()
        assert rows == [{"period": "2024-W02", "total_spending": 150.0}]

    def test_monthly_spending_groups_by_month(self, client):
        _create(client, "A", 100.0, datetime(2024, 1, 5))
        _create(client, "B", 50.0, datetime(2024, 2, 2))
        rows = client.get("/analytics/monthly-spending").json()
        assert rows == [
            {"period": "2024-01", "total_spending": 100.0},
            {"period": "2024-02", "total_spending": 50.0},
        ]