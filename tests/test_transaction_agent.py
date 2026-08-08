"""Focused tests for Phase 9 transaction-service agent integration.

No live LLM/API calls: the agent entry point and supporting services are
mocked so only create_transaction / batch behavior is exercised.
Run with:  .venv\\Scripts\\python.exe tests\\test_transaction_agent.py

Exit code 0 on success, 1 if any check fails.
"""

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import SQLModel, Session, create_engine

from app.schemas.agent import CategorizeOutcome
from app.schemas.transaction import TransactionCreate
import app.services.transaction as tx


def make_db():
    engine = create_engine("sqlite:///:memory:", poolclass=__import__("sqlalchemy").pool.StaticPool)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


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


results = []


def check(label, cond, detail=""):
    results.append((label, bool(cond), detail))
    print(("PASS" if cond else "FAIL"), "-", label, detail)


# 1. rule/feedback match via agent
with patch.object(tx, "run_categorization", return_value=outcome("Food", 1.0, "rule_engine", False)):
    db = make_db()
    r = tx.create_transaction(db, make_data("ALDI"))
    check("rule match", r["predicted_category"] == "Food" and r["prediction_source"] == "rule_engine"
          and r["requires_review"] is False and r["confidence"] == 1.0 and r["is_verified"] is False,
          f"src={r['prediction_source']} conf={r['confidence']}")

# 2. strong RAG
with patch.object(tx, "run_categorization", return_value=outcome("Fuel", 0.87, "rag", False)):
    db = make_db()
    r = tx.create_transaction(db, make_data("CALTEX"))
    check("strong RAG", r["predicted_category"] == "Fuel" and r["prediction_source"] == "rag"
          and r["confidence"] == 0.87 and r["requires_review"] is False,
          f"src={r['prediction_source']} conf={r['confidence']}")

# 3. weak RAG -> AI (agent resolved to AI with review flag)
with patch.object(tx, "run_categorization", return_value=outcome("Transport", 0.5, "ai", True)):
    db = make_db()
    r = tx.create_transaction(db, make_data("UBER"))
    check("weak RAG -> AI", r["predicted_category"] == "Transport" and r["prediction_source"] == "ai"
          and r["requires_review"] is True,
          f"src={r['prediction_source']} review={r['requires_review']}")

# 4. RAG failure -> AI (agent still returns AI outcome after retrieval failed)
with patch.object(tx, "run_categorization", return_value=outcome("Healthcare", 0.5, "ai", True)):
    db = make_db()
    r = tx.create_transaction(db, make_data("PHARMACY"))
    check("RAG failure -> AI", r["predicted_category"] == "Healthcare" and r["prediction_source"] == "ai",
          f"src={r['prediction_source']}")

# 5. agent failure -> legacy fallback (feedback/rule path)
with patch.object(tx, "run_categorization", side_effect=RuntimeError("agent boom")):
    with patch.object(tx, "predict_category", return_value="Education"):
        db = make_db()
        r = tx.create_transaction(db, make_data("KIPS SCHOOL"))
        check("agent failure -> legacy rule", r["predicted_category"] == "Education"
              and r["prediction_source"] == "rule_engine" and r["confidence"] == 1.0,
              f"src={r['prediction_source']}")

# 5b. agent failure -> legacy full pipeline (feedback miss, rag none, ai fallback)
with patch.object(tx, "run_categorization", side_effect=RuntimeError("agent boom")):
    with patch.object(tx, "predict_category", return_value="Uncategorized"):
        with patch.object(tx, "rag_categorize", return_value=None):
            with patch.object(tx, "predict_category_ai", return_value="Other"):
                db = make_db()
                r = tx.create_transaction(db, make_data("RANDOM SHOP"))
                check("fallback full pipeline", r["predicted_category"] == "Other"
                      and r["prediction_source"] == "ai" and r["requires_review"] is True,
                      f"src={r['prediction_source']}")

# 6. batch processing (each independently handled; agent mocked)
with patch.object(tx, "run_categorization", side_effect=[
    outcome("Food", 1.0, "rule_engine", False),
    outcome("Shopping", 0.5, "ai", True),
]):
    db = make_db()
    res = tx.create_transactions_batch(db, [make_data("MCDONALDS"), make_data("ASOS")])
    check("batch success both", len(res) == 2 and all(x["success"] for x in res),
          f"categories={[x['predicted_category'] for x in res]}")

# 6b. batch one failure -> independent handling (batch function unchanged, per-row try/except)
with patch.object(tx, "run_categorization", side_effect=[
    outcome("Food", 1.0, "rule_engine", False),
    RuntimeError("bad merchant"),
]):
    with patch.object(tx, "_categorize_sync", side_effect=RuntimeError("sync failure")):
        db = make_db()
        res = tx.create_transactions_batch(db, [make_data("MCD"), make_data("X")])
        check("batch independent", res[0]["success"] is True and res[1]["success"] is False,
              f"[{res[0]['success']}, {res[1]['success']}]")

# 7. FAIL test case preserved
db = make_db()
try:
    tx.create_transaction(db, make_data("FAIL"))
    check("FAIL preserves error", False, "no exception raised")
except Exception as e:
    check("FAIL preserves error", str(e) == "Intentional test error", f"exc={e}")

failed = [r for r in results if not r[1]]
print()
print("=" * 40)
print(f"{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)