"""Process reviews from Temu Claude Code."""

__version__ = "0.1.0"

# Import main functions for easier access
from .process_review import (
    load_review_data,
    validate_review,
    build_markdown,
    load_pull_request,
    derive_labels,
    apply_labels,
    publish_comment,
    approve_and_merge,
    main,
)

__all__ = [
    "load_review_data",
    "validate_review",
    "build_markdown",
    "load_pull_request",
    "derive_labels",
    "apply_labels",
    "publish_comment",
    "approve_and_merge",
    "main",
]
