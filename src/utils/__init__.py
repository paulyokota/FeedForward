"""Utility modules for FeedForward."""

from .normalize import (
    normalize_component,
    normalize_product_area,
    canonicalize_component,
    COMPONENT_ALIASES,
)

__all__ = [
    "normalize_component",
    "normalize_product_area",
    "canonicalize_component",
    "COMPONENT_ALIASES",
]
