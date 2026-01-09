"""
FeedForward API Client

Wrapper for FastAPI backend with typed responses.
Provides clean interface for Streamlit pages.
"""

import os
from typing import Any, Dict, List, Optional

import requests


class FeedForwardAPI:
    """
    Client for FeedForward FastAPI backend.

    Usage:
        api = FeedForwardAPI()
        metrics = api.get_dashboard_metrics()
        api.run_pipeline(days=7)
    """

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize API client.

        Args:
            base_url: API base URL. Defaults to localhost:8000.
        """
        self.base_url = base_url or os.getenv("API_URL", "http://localhost:8000")
        self.timeout = 30

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make GET request to API."""
        url = f"{self.base_url}{endpoint}"
        response = requests.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make POST request to API."""
        url = f"{self.base_url}{endpoint}"
        response = requests.post(url, json=data, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    # Health endpoints
    def health_check(self) -> Dict[str, Any]:
        """Check API health."""
        return self._get("/health")

    def health_full(self) -> Dict[str, Any]:
        """Full health check including database."""
        return self._get("/health/full")

    # Analytics endpoints
    def get_dashboard_metrics(self, days: int = 30) -> Dict[str, Any]:
        """Get dashboard metrics."""
        return self._get("/api/analytics/dashboard", {"days": days})

    def get_classification_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get detailed classification statistics."""
        return self._get("/api/analytics/stats", {"days": days})

    # Pipeline endpoints
    def run_pipeline(
        self,
        days: int = 7,
        max_conversations: Optional[int] = None,
        dry_run: bool = False,
        concurrency: int = 20,
    ) -> Dict[str, Any]:
        """Start a pipeline run."""
        data = {
            "days": days,
            "dry_run": dry_run,
            "concurrency": concurrency,
        }
        if max_conversations:
            data["max_conversations"] = max_conversations
        return self._post("/api/pipeline/run", data)

    def get_pipeline_status(self, run_id: int) -> Dict[str, Any]:
        """Get status of a pipeline run."""
        return self._get(f"/api/pipeline/status/{run_id}")

    def get_pipeline_history(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """Get pipeline run history."""
        return self._get("/api/pipeline/history", {"limit": limit, "offset": offset})

    def get_active_run(self) -> Dict[str, Any]:
        """Check if pipeline is currently running."""
        return self._get("/api/pipeline/active")

    # Theme endpoints
    def get_trending_themes(
        self,
        days: int = 7,
        min_occurrences: int = 2,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Get trending themes."""
        return self._get("/api/themes/trending", {
            "days": days,
            "min_occurrences": min_occurrences,
            "limit": limit,
        })

    def get_orphan_themes(
        self,
        threshold: int = 2,
        days: int = 30,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Get orphan (low-count) themes."""
        return self._get("/api/themes/orphans", {
            "threshold": threshold,
            "days": days,
            "limit": limit,
        })

    def get_singleton_themes(self, days: int = 30, limit: int = 50) -> Dict[str, Any]:
        """Get singleton themes (count=1)."""
        return self._get("/api/themes/singletons", {"days": days, "limit": limit})

    def list_themes(
        self,
        product_area: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List all themes with optional filtering."""
        params = {"limit": limit, "offset": offset}
        if product_area:
            params["product_area"] = product_area
        return self._get("/api/themes/all", params)

    def get_theme_detail(self, signature: str) -> Dict[str, Any]:
        """Get detailed theme information."""
        return self._get(f"/api/themes/{signature}")
