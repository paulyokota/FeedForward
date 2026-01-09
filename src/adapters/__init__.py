"""
Source Adapters
Normalize different data sources into common conversation format.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class NormalizedConversation:
    """Common format for all data sources."""

    id: str
    text: str
    data_source: str
    source_metadata: Dict
    created_at: datetime
    url: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "text": self.text,
            "data_source": self.data_source,
            "source_metadata": self.source_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "url": self.url,
        }


class SourceAdapter(ABC):
    """Base class for data source adapters."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the name of this data source."""
        pass

    @abstractmethod
    def fetch(self, **kwargs) -> List[Dict]:
        """Fetch raw data from source."""
        pass

    @abstractmethod
    def normalize(self, raw_data: Dict) -> NormalizedConversation:
        """Normalize to common conversation format."""
        pass

    def fetch_and_normalize(self, **kwargs) -> List[NormalizedConversation]:
        """Fetch data and normalize all items."""
        raw_items = self.fetch(**kwargs)
        return [self.normalize(item) for item in raw_items]


# Import adapters for convenience
from .coda_adapter import CodaAdapter
from .intercom_adapter import IntercomAdapter

__all__ = [
    "SourceAdapter",
    "NormalizedConversation",
    "CodaAdapter",
    "IntercomAdapter",
]
