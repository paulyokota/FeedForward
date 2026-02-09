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
import logging.handlers
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from src.logging_utils import SafeStreamHandler

# =============================================================================
# File-based logging (survives stdout/pipe issues)
# =============================================================================
# This ensures we capture stack traces even when stdout is unavailable
# (e.g., detached terminal, broken pipe). Log file: /tmp/feedforward-app.log
_LOG_FILE = "/tmp/feedforward-app.log"
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Configure root logger with both file and stream handlers
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)

# File handler - always works, captures everything
_file_handler = logging.handlers.RotatingFileHandler(
    _LOG_FILE,
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=3,
)
_file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
_file_handler.setLevel(logging.INFO)
_root_logger.addHandler(_file_handler)

# Stream handler - uses SafeStreamHandler to gracefully handle broken pipes (Issue #185)
_stream_handler = SafeStreamHandler()
_stream_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
_stream_handler.setLevel(logging.INFO)
_root_logger.addHandler(_stream_handler)

# Suppress noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)

# =============================================================================

# Load .env from project root so env vars like HYBRID_CLUSTERING_ENABLED are available
load_dotenv(Path(__file__).parent.parent.parent / ".env")
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import analytics, discovery, health, labels, pipeline, research, stories, sync, themes
from src.db.connection import get_connection

logger = logging.getLogger(__name__)


def cleanup_stale_pipeline_runs() -> int:
    """
    Mark any in-progress pipeline runs as 'failed' on startup.

    This handles the case where the server was restarted while a pipeline
    was running or stopping, leaving stale status in the database.

    Note: This assumes single-instance deployment. Multi-instance deployments
    would require a heartbeat mechanism to distinguish truly stale runs.

    Returns:
        Number of stale runs cleaned up, or -1 if cleanup failed.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE pipeline_runs
                    SET status = 'failed',
                        completed_at = NOW(),
                        error_message = 'Pipeline interrupted by server restart. You can safely start a new run.'
                    WHERE status IN ('running', 'stopping')
                    RETURNING id
                    """
                )
                stale_ids = [row[0] for row in cur.fetchall()]

        if stale_ids:
            logger.warning(
                f"Cleaned up {len(stale_ids)} stale pipeline run(s) from previous session: {stale_ids}"
            )
        return len(stale_ids)

    except Exception as e:
        logger.error(
            f"Failed to cleanup stale pipeline runs (stale runs may appear stuck in UI): {e}"
        )
        return -1


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown tasks."""
    cleanup_stale_pipeline_runs()
    yield


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
app.include_router(discovery.router)


@app.get("/")
def root():
    """Root endpoint with API information."""
    return {
        "name": "FeedForward API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }
