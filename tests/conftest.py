"""
Pytest configuration for FeedForward tests.

Adds project root to sys.path so tests can import from src/.
"""

import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
