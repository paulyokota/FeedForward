"""
Search Source Adapters

Adapters for extracting searchable content from different data sources.
Each adapter implements the SearchSourceAdapter interface.
"""

from .base import SearchSourceAdapter
from .coda_adapter import CodaSearchAdapter
from .intercom_adapter import IntercomSearchAdapter

__all__ = [
    "SearchSourceAdapter",
    "CodaSearchAdapter",
    "IntercomSearchAdapter",
]
