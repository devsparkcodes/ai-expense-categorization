import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.api.analytics import router as analytics_router
from app.api.transaction import router as transaction_router
from app.core.logging import setup_logging
from app.database.database import create_db_and_tables

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run application startup/shutdown lifecycle events."""
    setup_logging()
    logger.info("Starting application")
    create_db_and_tables()
    yield
    logger.info("Application shutdown complete")


app = FastAPI(lifespan=lifespan)

app.include_router(transaction_router)
app.include_router(analytics_router)


@app.get("/health", status_code=200)
def health() -> dict:
    """Simple health check endpoint."""
    return {"status": "healthy"}


def main() -> None:
    """Run the application in production mode.

    Binds to 0.0.0.0 on the port from the PORT environment variable
    (default 8000). Invoke with: python -m app.main
    """
    import os

    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port)


if __name__ == "__main__":
    main()
