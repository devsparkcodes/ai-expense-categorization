from fastapi import FastAPI

from app.api.analytics import router as analytics_router
from app.api.transaction import router as transaction_router
from app.database.database import create_db_and_tables

app = FastAPI()

app.include_router(transaction_router)
app.include_router(analytics_router)


@app.on_event("startup")
def startup():
    """Create all database tables when the application starts."""
    create_db_and_tables()

