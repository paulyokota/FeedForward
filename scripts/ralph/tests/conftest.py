"""
Pytest configuration for Ralph V2 tests.

Adds the parent directory to sys.path so tests can import modules.
"""

import sys
from pathlib import Path

# Add parent directory (scripts/ralph) to path for imports
RALPH_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(RALPH_DIR))
