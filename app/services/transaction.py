import logging
from datetime import date, datetime, time
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session, func, or_, select

from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate
from app.models.category_feedback import CategoryFeedback
from app.agents.categorization_agent import run_categorization
from app.services.categorizer import predict_category
from app.services.ai_categorizer import predict_category_ai
from app.services.rag_service import rag_categorize


def _categorize_sync(merchant_name: str, db: Session) -> tuple:
    """Legacy synchronous pipeline: Feedback -> Rule Engine -> RAG -> AI."""
    predicted_category = predict_category(merchant_name, db=db)
    if predicted_category != "Uncategorized":
        return predicted_category, 1.0, "rule_engine", False

    rag_result = None
    try:
        rag_result = rag_categorize(merchant_name, db=db)
    except Exception as exc:
        logging.exception("RAG service failed for merchant '%s': %s", merchant_name, exc)

    if rag_result and rag_result.get("source") == "rag":
        return rag_result["category"], rag_result["confidence"], "rag", False

    context = None
    if rag_result and rag_result.get("source") == "rag_context":
        context = rag_result.get("context")
    return predict_category_ai(merchant_name, context=context), 0.5, "ai", True


def create_transaction(db: Session, transaction_data: TransactionCreate) -> dict:
    if transaction_data.merchant_name == "FAIL":
        raise Exception("Intentional test error")

    try:
        outcome = run_categorization(transaction_data.merchant_name, db=db)
        predicted_category = outcome.category
        confidence = outcome.confidence
        prediction_source = outcome.prediction_source
        requires_review = outcome.requires_review
    except Exception as exc:
        logging.exception(
            "Categorization agent failed for merchant '%s'; falling back to synchronous pipeline: %s",
            transaction_data.merchant_name,
            exc,
        )
        (
            predicted_category,
            confidence,
            prediction_source,
            requires_review,
        ) = _categorize_sync(transaction_data.merchant_name, db=db)
    db_transaction = Transaction(
        **transaction_data.model_dump(),
        predicted_category=predicted_category,
        confidence=confidence,
        prediction_source=prediction_source,
        requires_review=requires_review,
        is_verified=False,
    )
    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    return db_transaction.model_dump()


def create_transactions_batch(
    db: Session, transactions: list[TransactionCreate]
) -> list:
    results = []
    for transaction_data in transactions:
        try:
            created = create_transaction(db=db, transaction_data=transaction_data)
            results.append(
                {
                    "success": True,
                    "transaction_id": created["id"],
                    "merchant_name": created["merchant_name"],
                    "predicted_category": created["predicted_category"],
                }
            )
        except Exception as exc:
            results.append(
                {
                    "success": False,
                    "transaction_id": None,
                    "merchant_name": transaction_data.merchant_name,
                    "predicted_category": None,
                    "error": str(exc),
                }
            )
    return results


_SORT_COLUMNS = {
    "transaction_date": Transaction.transaction_date,
    "amount": Transaction.amount,
    "merchant_name": Transaction.merchant_name,
}


def get_transactions(
    db: Session,
    category: Optional[str] = None,
    merchant: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    sort_by: str = "transaction_date",
    order: str = "desc",
    page: int = 1,
    limit: int = 10,
) -> list:
    """List transactions with optional filtering, search, sorting, and pagination."""
    if sort_by not in _SORT_COLUMNS:
        raise HTTPException(status_code=400, detail=f"Invalid sort_by: {sort_by}")
    if order not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail=f"Invalid order: {order}")
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be > 0")

    query = select(Transaction)

    if category:
        query = query.where(
            func.lower(Transaction.predicted_category) == category.lower()
        )
    if merchant:
        pattern = f"%{merchant.lower()}%"
        query = query.where(func.lower(Transaction.merchant_name).like(pattern))
    if search:
        pattern = f"%{search.lower()}%"
        query = query.where(
            or_(
                func.lower(Transaction.merchant_name).like(pattern),
                func.lower(Transaction.description).like(pattern),
            )
        )
    if start_date:
        query = query.where(
            Transaction.transaction_date >= datetime.combine(start_date, time.min)
        )
    if end_date:
        query = query.where(
            Transaction.transaction_date <= datetime.combine(end_date, time.max)
        )

    column = _SORT_COLUMNS[sort_by]
    query = query.order_by(column.asc() if order == "asc" else column.desc())

    offset = (page - 1) * limit
    transactions = db.exec(query.offset(offset).limit(limit)).all()
    return [t.model_dump() for t in transactions]


def get_transaction(db: Session, transaction_id: UUID) -> dict:
    transaction = db.exec(
        select(Transaction).where(Transaction.id == transaction_id)
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return transaction.model_dump()


def update_transaction(
    db: Session, transaction_id: UUID, transaction_data: TransactionCreate
) -> dict:
    transaction = db.exec(
        select(Transaction).where(Transaction.id == transaction_id)
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    transaction.merchant_name = transaction_data.merchant_name
    transaction.amount = transaction_data.amount
    transaction.currency = transaction_data.currency
    transaction.description = transaction_data.description
    transaction.transaction_date = transaction_data.transaction_date
    db.commit()
    db.refresh(transaction)
    return transaction.model_dump()


def delete_transaction(db: Session, transaction_id: UUID) -> dict:
    transaction = db.exec(
        select(Transaction).where(Transaction.id == transaction_id)
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    db.delete(transaction)
    db.commit()
    return {"message": "Transaction deleted successfully."}


def update_transaction_category(
    db: Session, transaction_id: UUID, category: str
) -> dict:
    transaction = db.exec(
        select(Transaction).where(Transaction.id == transaction_id)
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    feedback = CategoryFeedback(
        merchant_name=transaction.merchant_name,
        original_category=transaction.predicted_category,
        corrected_category=category,
    )
    db.add(feedback)
    db.commit()
    transaction.predicted_category = category
    transaction.is_verified = True
    transaction.requires_review = False
    transaction.prediction_source = "manual"
    db.commit()
    db.refresh(transaction)
    return transaction.model_dump()
