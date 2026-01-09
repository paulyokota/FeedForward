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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import analytics, health, pipeline, themes

# Create FastAPI application
app = FastAPI(
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

# Configure CORS for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",  # Streamlit default
        "http://127.0.0.1:8501",
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


@app.get("/")
def root():
    """Root endpoint with API information."""
    return {
        "name": "FeedForward API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }
