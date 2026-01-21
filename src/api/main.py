"""
FeedForward API - Main Application

FastAPI application providing REST endpoints for operational visibility
into the FeedForward conversation analysis pipeline.

Run with:
    uvicorn src.api.main:app --reload --port 8000

API Documentation available at:
    - Swagger UI: http://localhost:8000/docs
    - ReDoc: http://localhost:8000/redoc
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import analytics, health, labels, pipeline, research, stories, sync, themes
from src.db.connection import get_connection

logger = logging.getLogger(__name__)


def cleanup_stale_pipeline_runs() -> int:
    """
    Mark any 'running' pipeline runs as 'failed' on startup.

    This handles the case where the server was restarted while a pipeline
    was running, leaving stale 'running' status in the database.

    Returns:
        Number of stale runs cleaned up.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE pipeline_runs
                    SET status = 'failed',
                        completed_at = NOW(),
                        error_message = 'Process terminated unexpectedly (server restart)'
                    WHERE status = 'running'
                    RETURNING id
                    """
                )
                stale_ids = [row[0] for row in cur.fetchall()]
            conn.commit()

        if stale_ids:
            logger.warning(
                f"Cleaned up {len(stale_ids)} stale pipeline run(s) from previous session: {stale_ids}"
            )
        return len(stale_ids)

    except Exception as e:
        logger.error(f"Failed to cleanup stale pipeline runs: {e}")
        return 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown tasks."""
    # Startup
    cleanup_stale_pipeline_runs()
    yield
    # Shutdown (nothing needed currently)


# Create FastAPI application
app = FastAPI(
    lifespan=lifespan,
    title="FeedForward API",
    description="""
    Operational API for the FeedForward conversation analysis pipeline.

    ## Features

    - **Pipeline Control**: Kick off runs, check status, view history
    - **Theme Analysis**: Browse trending themes, orphans, and singletons
    - **Analytics**: Dashboard metrics and classification distribution

    ## Architecture

    This API wraps the existing FeedForward pipeline to provide:
    - REST endpoints for programmatic access
    - Streamlit frontend integration
    - Future multi-source ingestion support
    """,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS for frontend applications
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",  # Streamlit default
        "http://127.0.0.1:8501",
        "http://localhost:3000",  # Next.js default
        "http://127.0.0.1:3000",
        "http://localhost:3001",  # Next.js alternate port
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router)
app.include_router(analytics.router)
app.include_router(pipeline.router)
app.include_router(themes.router)
app.include_router(stories.router)
app.include_router(sync.router)
app.include_router(labels.router)
app.include_router(research.router)


@app.get("/")
def root():
    """Root endpoint with API information."""
    return {
        "name": "FeedForward API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }
