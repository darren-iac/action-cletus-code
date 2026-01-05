"""Cletus Code - AI-powered pull request review."""

__version__ = "0.4.0"

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
    main as process_review_main,
)
from .run_review import ReviewOrchestrator, main as run_review_main

__all__ = [
    "load_review_data",
    "validate_review",
    "build_markdown",
    "load_pull_request",
    "derive_labels",
    "apply_labels",
    "publish_comment",
    "approve_and_merge",
    "process_review_main",
    "ReviewOrchestrator",
    "run_review_main",
]
# Test comment
# Another test
