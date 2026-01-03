"""Pytest configuration and fixtures for process_review tests."""

import sys
from pathlib import Path

# Add .github directory to path for proper package imports
# The process_review package is under .github/process_review/
GITHUB_DIR = str(Path(__file__).resolve().parent.parent.parent)
if GITHUB_DIR not in sys.path:
    sys.path.insert(0, GITHUB_DIR)


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (deselect with '-m \"not integration\"')"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running"
    )
