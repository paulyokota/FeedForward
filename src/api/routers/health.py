"""
Health Check Endpoints

Provides health and readiness checks for the FeedForward API.
Used by monitoring systems and load balancers.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.deps import get_db


router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Basic health check response."""
    status: str
    timestamp: datetime


class DatabaseHealthResponse(BaseModel):
    """Database connectivity check response."""
    connected: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class FullHealthResponse(BaseModel):
    """Complete system health status."""
    status: str
    timestamp: datetime
    database: DatabaseHealthResponse


@router.get("/health", response_model=HealthResponse)
def health_check():
    """
    Basic health check endpoint.

    Returns 200 OK if the API is running.
    Does not check external dependencies.
    """
    return HealthResponse(
        status="ok",
        timestamp=datetime.utcnow()
    )


@router.get("/health/db", response_model=DatabaseHealthResponse)
def database_health_check(db=Depends(get_db)):
    """
    Database connectivity check.

    Executes a simple query to verify database is reachable.
    Returns connection status and latency.
    """
    import time

    try:
        start = time.time()
        with db.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        latency = (time.time() - start) * 1000  # Convert to ms

        return DatabaseHealthResponse(
            connected=True,
            latency_ms=round(latency, 2)
        )
    except Exception as e:
        return DatabaseHealthResponse(
            connected=False,
            error=str(e)
        )


@router.get("/health/full", response_model=FullHealthResponse)
def full_health_check(db=Depends(get_db)):
    """
    Complete system health check.

    Checks all dependencies and returns aggregate status.
    Returns 'healthy' only if all checks pass.
    """
    import time

    # Check database
    try:
        start = time.time()
        with db.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        latency = (time.time() - start) * 1000

        db_health = DatabaseHealthResponse(
            connected=True,
            latency_ms=round(latency, 2)
        )
    except Exception as e:
        db_health = DatabaseHealthResponse(
            connected=False,
            error=str(e)
        )

    # Determine overall status
    overall_status = "healthy" if db_health.connected else "unhealthy"

    return FullHealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        database=db_health
    )
