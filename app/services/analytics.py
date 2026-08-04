from sqlmodel import Session, func, select

from app.models.transaction import Transaction


def get_summary(db: Session) -> dict:
    row = db.exec(
        select(
            func.count(Transaction.id),
            func.sum(Transaction.amount),
            func.avg(Transaction.amount),
            func.max(Transaction.amount),
        )
    ).one()
    count, total_spending, average, highest = row
    return {
        "total_transactions": count,
        "total_spending": float(total_spending or 0),
        "average_transaction": float(average or 0),
        "highest_transaction": float(highest or 0),
    }
