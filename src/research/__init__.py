"""
Research Module

Provides unified search and RAG capabilities across multiple data sources
(Coda research, Intercom conversations, etc.).

Key Components:
- UnifiedSearchService: Semantic search across all sources
- EmbeddingPipeline: Batch embedding generation
- Source Adapters: Extract content from different sources
"""

from .models import (
    SearchableContent,
    UnifiedSearchResult,
    UnifiedSearchRequest,
    SimilarContentRequest,
    SuggestedEvidence,
    SearchErrorResponse,
)
from .unified_search import UnifiedSearchService
from .embedding_pipeline import EmbeddingPipeline

__all__ = [
    "SearchableContent",
    "UnifiedSearchResult",
    "UnifiedSearchRequest",
    "SimilarContentRequest",
    "SuggestedEvidence",
    "SearchErrorResponse",
    "UnifiedSearchService",
    "EmbeddingPipeline",
]
