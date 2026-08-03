from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate


def create_transaction(db: Session, transaction_data: TransactionCreate) -> dict:
    db_transaction = Transaction(
        **transaction_data.model_dump(),
        predicted_category="Uncategorized",
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
