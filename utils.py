"""Utility functions for process_review."""

import re
from collections import defaultdict
from typing import Dict


def truncate(text: str, limit: int = 300) -> str:
    """Truncate text to a maximum length, adding "..." if truncated.

    Args:
        text: The text to truncate.
        limit: Maximum length before truncation.

    Returns:
        Truncated text with "..." appended if shortened.
    """
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def normalize_risk(value: str | None) -> str:
    """Normalize risk value to uppercase, defaulting to UNKNOWN.

    Args:
        value: Risk value (e.g., "low", "Medium", None).

    Returns:
        Normalized uppercase risk value or "UNKNOWN".
    """
    return (value or "UNKNOWN").upper()


# Priority ordering for risk levels (lower = higher priority)
_RISK_PRIORITY: Dict[str, int] = {
    "HIGH": 0,
    "MEDIUM": 1,
    "LOW": 2,
    "UNKNOWN": 3,
}


def risk_sort_key(value: str | None) -> int:
    """Get sort key for risk level (HIGH sorts first).

    Args:
        value: Risk value to get sort key for.

    Returns:
        Integer sort key (lower = higher priority).
    """
    normalized = normalize_risk(value)
    return _RISK_PRIORITY.get(normalized, len(_RISK_PRIORITY))


# Regular expression for creating URL-safe anchors
_ANCHOR_ALLOWED_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, fallback: str) -> str:
    """Convert text to a URL-safe slug.

    Args:
        text: Text to slugify.
        fallback: Default value if text is empty or results in empty slug.

    Returns:
        URL-safe slug string.
    """
    normalized = (text or "").strip().lower()
    slug = _ANCHOR_ALLOWED_RE.sub("-", normalized).strip("-")
    return slug or fallback


def make_anchor(counter: defaultdict, prefix: str, text: str, fallback: str) -> str:
    """Create a unique anchor ID, handling duplicates.

    Args:
        counter: defaultdict(int) for tracking duplicates.
        prefix: Optional prefix for the anchor (e.g., "resource").
        text: Text to slugify for the anchor.
        fallback: Default value if text is empty.

    Returns:
        Unique anchor ID with suffix for duplicates.
    """
    base = slugify(text, fallback)
    anchor = f"{prefix}-{base}" if prefix else base
    if counter[anchor]:
        suffix = counter[anchor]
        counter[anchor] += 1
        return f"{anchor}-{suffix}"
    counter[anchor] += 1
    return anchor


def format_resource(resource: object) -> str:
    """Format a resource identifier from a string or mapping."""
    if isinstance(resource, str):
        return resource.strip()
    if isinstance(resource, dict):
        kind = resource.get("kind", "?")
        namespace = resource.get("namespace") or "default"
        name = resource.get("name", "?")
        return f"{kind}/{namespace}/{name}"
    return ""
