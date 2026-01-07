"""
Analytics module for FeedForward pipeline.

Provides analysis tools for documentation coverage, theme trends, and quality metrics.
"""

from .doc_coverage import (
    DocumentationCoverageAnalyzer,
    ThemeGap,
    ArticleGap,
    ProductAreaCoverage,
    CoverageReport
)

__all__ = [
    'DocumentationCoverageAnalyzer',
    'ThemeGap',
    'ArticleGap',
    'ProductAreaCoverage',
    'CoverageReport',
]
