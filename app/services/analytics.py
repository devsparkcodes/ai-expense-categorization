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


def get_category_breakdown(db: Session) -> list:
    rows = db.exec(
        select(
            Transaction.predicted_category,
            func.sum(Transaction.amount),
            func.count(Transaction.id),
        )
        .group_by(Transaction.predicted_category)
        .order_by(func.sum(Transaction.amount).desc())
    ).all()
    return [
        {
            "category": category,
            "total_spending": float(total_spending or 0),
            "transaction_count": count,
        }
        for category, total_spending, count in rows
    ]


def get_top_merchants(db: Session) -> list:
    rows = db.exec(
        select(
            Transaction.merchant_name,
            func.sum(Transaction.amount),
            func.count(Transaction.id),
        )
        .group_by(Transaction.merchant_name)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(10)
    ).all()
    return [
        {
            "merchant": merchant,
            "total_spending": float(total_spending or 0),
            "transaction_count": count,
        }
        for merchant, total_spending, count in rows
    ]
