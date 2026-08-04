from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database.database import get_session
from app.schemas.analytics import AnalyticsSummaryResponse
from app.services.analytics import get_summary

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary", status_code=200, response_model=AnalyticsSummaryResponse)
def summary(db: Session = Depends(get_session)):
    return get_summary(db=db)
