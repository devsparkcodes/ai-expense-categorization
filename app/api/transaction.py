from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.database.database import get_session
from app.schemas.transaction import TransactionBatchResult, TransactionCreate
from app.services.transaction import (
    create_transaction as _create_transaction,
    create_transactions_batch as _create_transactions_batch,
    delete_transaction as _delete_transaction,
    get_transaction as _get_transaction,
    get_transactions as _get_transactions,
    update_transaction as _update_transaction,
    update_transaction_category as _update_transaction_category,
)

router = APIRouter(prefix="/transactions", tags=["Transactions"])


class CategoryUpdate(BaseModel):
    category: str


@router.get("/", status_code=200)
def get_transactions(
    db: Session = Depends(get_session),
    category: Optional[str] = None,
    merchant: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    sort_by: str = "transaction_date",
    order: str = "desc",
    page: int = 1,
    limit: int = 10,
):
    """List transactions with optional filtering, search, sorting, and pagination."""
    return _get_transactions(
        db=db,
        category=category,
        merchant=merchant,
        search=search,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        order=order,
        page=page,
        limit=limit,
    )


@router.get("/{transaction_id}", status_code=200)
def get_transaction(
    transaction_id: UUID,
    db: Session = Depends(get_session),
):
    return _get_transaction(db=db, transaction_id=transaction_id)


@router.put("/{transaction_id}", status_code=200)
def update_transaction(
    transaction_id: UUID,
    transaction_data: TransactionCreate,
    db: Session = Depends(get_session),
):
    return _update_transaction(
        db=db, transaction_id=transaction_id, transaction_data=transaction_data
    )


@router.post("/batch", status_code=200, response_model=list[TransactionBatchResult])
def create_transactions_batch(
    transactions: list[TransactionCreate],
    db: Session = Depends(get_session),
):
    return _create_transactions_batch(db=db, transactions=transactions)


@router.post("/", status_code=201)
def create_transaction(
    transaction: TransactionCreate,
    db: Session = Depends(get_session),
):
    return _create_transaction(db=db, transaction_data=transaction)


@router.delete("/{transaction_id}", status_code=200)
def delete_transaction(
    transaction_id: UUID,
    db: Session = Depends(get_session),
):
    return _delete_transaction(db=db, transaction_id=transaction_id)


@router.patch("/{transaction_id}/category", status_code=200)
def update_transaction_category(
    transaction_id: UUID,
    category_data: CategoryUpdate,
    db: Session = Depends(get_session),
):
    return _update_transaction_category(
        db=db, transaction_id=transaction_id, category=category_data.category
    )
