from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate
from app.models.category_feedback import CategoryFeedback
from app.services.categorizer import predict_category
from app.services.ai_categorizer import predict_category_ai


def create_transaction(db: Session, transaction_data: TransactionCreate) -> dict:
    predicted_category = predict_category(transaction_data.merchant_name, db=db)
    if predicted_category != "Uncategorized":
        confidence = 1.0
        prediction_source = "rule_engine"
        requires_review = False
    else:
        predicted_category = predict_category_ai(transaction_data.merchant_name)
        confidence = 0.5
        prediction_source = "ai"
        requires_review = True
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


def get_transactions(db: Session) -> list:
    transactions = db.exec(select(Transaction)).all()
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
