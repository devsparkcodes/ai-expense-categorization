from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database.database import get_session
from app.schemas.analytics import (
    AnalyticsSummaryResponse,
    CategoryBreakdownItem,
    TopMerchantItem,
)
from app.services.analytics import get_category_breakdown, get_summary, get_top_merchants

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary", status_code=200, response_model=AnalyticsSummaryResponse)
def summary(db: Session = Depends(get_session)):
    return get_summary(db=db)


@router.get("/category-breakdown", status_code=200, response_model=list[CategoryBreakdownItem])
def category_breakdown(db: Session = Depends(get_session)):
    return get_category_breakdown(db=db)


@router.get("/top-merchants", status_code=200, response_model=list[TopMerchantItem])
def top_merchants(db: Session = Depends(get_session)):
    return get_top_merchants(db=db)
