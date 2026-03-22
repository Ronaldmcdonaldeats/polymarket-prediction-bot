#!/usr/bin/env python3
"""
Conversion utilities for probability representations.
"""

from typing import Union


def pct_to_decimal(percentage: Union[int, float, str]) -> float:
    """
    Convert percentage (0-100) to decimal (0-1).

    Args:
        percentage: Value as percentage (e.g., 50 for 50%)

    Returns:
        Decimal value (e.g., 0.5)
    """
    try:
        pct = float(percentage)
        return pct / 100.0
    except (ValueError, TypeError):
        return 0.5  # sensible default


def decimal_to_pct(decimal: Union[int, float, str]) -> float:
    """
    Convert decimal (0-1) to percentage (0-100).

    Args:
        decimal: Value as decimal (e.g., 0.5 for 50%)

    Returns:
        Percentage value (e.g., 50.0)
    """
    try:
        d = float(decimal)
        return d * 100.0
    except (ValueError, TypeError):
        return 50.0  # sensible default


def smart_truncate(text: str, max_length: int = 200) -> str:
    """
    Truncate text cleanly without cutting words in half.
    If text exceeds max_length, truncate at last word boundary and add ellipsis.

    Args:
        text: The text to truncate
        max_length: Maximum length including ellipsis

    Returns:
        Cleanly truncated text
    """
    if not text:
        return ""

    text = str(text).strip()
    if len(text) <= max_length:
        return text

    # Truncate at word boundary
    truncated = text[:max_length - 3].rsplit(' ', 1)[0]
    return truncated + "..."
