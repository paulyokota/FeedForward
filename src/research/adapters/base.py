"""
Base Search Source Adapter

Abstract base class for extracting searchable content from different sources.
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Iterator, List, Optional

from ..models import SearchableContent

logger = logging.getLogger(__name__)


class SearchSourceAdapter(ABC):
    """
    Abstract base class for search source adapters.

    Each adapter extracts content from a specific source (Coda, Intercom, etc.)
    and normalizes it into SearchableContent for embedding.
    """

    @abstractmethod
    def get_source_type(self) -> str:
        """
        Returns source identifier.

        Examples: 'coda_page', 'coda_theme', 'intercom'
        """
        pass

    @abstractmethod
    def extract_content(self, source_id: str) -> Optional[SearchableContent]:
        """
        Extract content for a specific item.

        Args:
            source_id: Unique identifier within this source

        Returns:
            SearchableContent if found, None otherwise
        """
        pass

    @abstractmethod
    def extract_all(self, limit: Optional[int] = None) -> Iterator[SearchableContent]:
        """
        Extract all content from this source.

        Args:
            limit: Maximum items to extract (for testing)

        Yields:
            SearchableContent for each item
        """
        pass

    @abstractmethod
    def get_source_url(self, source_id: str) -> str:
        """
        Get URL to view original source.

        Args:
            source_id: Source item identifier

        Returns:
            URL string
        """
        pass

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """
        Compute SHA-256 hash of content for change detection.

        Args:
            content: Text content to hash

        Returns:
            Hex string of SHA-256 hash
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    @staticmethod
    def create_snippet(content: str, max_length: int = 200) -> str:
        """
        Create a snippet from content.

        Args:
            content: Full text content
            max_length: Maximum snippet length

        Returns:
            Truncated content with ellipsis if needed
        """
        if len(content) <= max_length:
            return content

        # Find a good break point (end of sentence or word)
        truncated = content[:max_length]
        last_period = truncated.rfind('.')
        last_space = truncated.rfind(' ')

        if last_period > max_length * 0.5:
            return truncated[:last_period + 1]
        elif last_space > max_length * 0.5:
            return truncated[:last_space] + '...'
        else:
            return truncated + '...'
