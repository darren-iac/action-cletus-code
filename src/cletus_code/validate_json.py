"""Validate review.json against the schema and required fields.

This module provides validation to ensure the structured output from the review
process is well-formed and contains all required fields before proceeding.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, List

logger = logging.getLogger(__name__)


# Required fields for a valid review
REQUIRED_FIELDS = ["approved", "overallRisk", "summary", "findings"]

# Valid risk levels
VALID_RISK_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NEGLIGIBLE"]

# Finding type validation - removed to allow AI flexibility
# The AI can generate many descriptive types, so we only validate
# that it's a non-empty string rather than restricting to an enum
# VALID_FINDING_TYPES = [...]  # Disabled


class ReviewValidationError(Exception):
    """Raised when review.json validation fails."""

    def __init__(self, message: str, missing_fields: List[str] = None):
        super().__init__(message)
        self.missing_fields = missing_fields or []


def validate_review_json(json_path: Path, schema_path: Path = None) -> None:
    """Validate review.json against required fields and optional schema.

    Args:
        json_path: Path to review.json file.
        schema_path: Optional path to JSON schema for additional validation.

    Raises:
        ReviewValidationError: If validation fails.
        FileNotFoundError: If review.json doesn't exist.
        json.JSONDecodeError: If review.json is not valid JSON.
    """
    if not json_path.exists():
        raise FileNotFoundError(f"Review file not found: {json_path}")

    # Load and parse JSON
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"Invalid JSON in {json_path}: {e.msg}",
            e.doc,
            e.pos
        )

    # Validate that it's a dict
    if not isinstance(data, dict):
        raise ReviewValidationError(
            f"Review must be a JSON object, got {type(data).__name__}"
        )

    # Check required top-level fields
    missing_fields = [
        field for field in REQUIRED_FIELDS if field not in data
    ]

    if missing_fields:
        raise ReviewValidationError(
            f"Review missing required fields: {', '.join(missing_fields)}",
            missing_fields=missing_fields
        )

    # Validate field types and values
    _validate_field_types(data)

    # Validate findings array
    if "findings" in data:
        _validate_findings(data["findings"])

    # Optional: Validate against JSON schema if provided
    if schema_path and schema_path.exists():
        _validate_against_schema(data, schema_path)

    logger.info(f"Review JSON validation passed: {json_path}")


def _validate_field_types(data: dict[str, Any]) -> None:
    """Validate that required fields have the correct type.

    Args:
        data: Parsed JSON data.

    Raises:
        ReviewValidationError: If any field has wrong type.
    """
    # approved must be boolean
    if not isinstance(data["approved"], bool):
        raise ReviewValidationError(
            f"'approved' must be boolean, got {type(data['approved']).__name__}"
        )

    # overallRisk must be string and valid value
    if not isinstance(data["overallRisk"], str):
        raise ReviewValidationError(
            f"'overallRisk' must be string, got {type(data['overallRisk']).__name__}"
        )

    if data["overallRisk"] not in VALID_RISK_LEVELS:
        raise ReviewValidationError(
            f"'overallRisk' must be one of {VALID_RISK_LEVELS}, got '{data['overallRisk']}'"
        )

    # summary must be string
    if not isinstance(data["summary"], str):
        raise ReviewValidationError(
            f"'summary' must be string, got {type(data['summary']).__name__}"
        )

    # findings must be list
    if not isinstance(data["findings"], list):
        raise ReviewValidationError(
            f"'findings' must be array, got {type(data['findings']).__name__}"
        )


def _validate_findings(findings: list[Any]) -> None:
    """Validate the findings array.

    Args:
        findings: List of finding objects.

    Raises:
        ReviewValidationError: If any finding is invalid.
    """
    for i, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise ReviewValidationError(
                f"Finding {i} must be object, got {type(finding).__name__}"
            )

        # Check required finding fields
        required = ["type", "title", "summary", "risk"]
        missing = [f for f in required if f not in finding]

        if missing:
            raise ReviewValidationError(
                f"Finding {i} missing required fields: {', '.join(missing)}"
            )

        # Validate finding fields
        # Type validation removed - AI can generate descriptive types
        if not isinstance(finding["type"], str) or not finding["type"].strip():
            raise ReviewValidationError(
                f"Finding {i}: type must be a non-empty string, got {type(finding['type']).__name__}"
            )

        if finding["risk"] not in VALID_RISK_LEVELS:
            raise ReviewValidationError(
                f"Finding {i}: risk must be one of {VALID_RISK_LEVELS}, got '{finding['risk']}'"
            )


def _validate_against_schema(data: dict[str, Any], schema_path: Path) -> None:
    """Validate against JSON schema if jsonschema library is available.

    Args:
        data: Parsed JSON data.
        schema_path: Path to JSON schema file.

    Raises:
        ReviewValidationError: If validation against schema fails.
    """
    try:
        import jsonschema
    except ImportError:
        logger.warning("jsonschema library not available, skipping schema validation")
        return

    # Load schema
    with open(schema_path, 'r') as f:
        schema = json.load(f)

    # Validate
    try:
        jsonschema.validate(instance=data, schema=schema)
        logger.info("Review JSON validates against schema")
    except jsonschema.ValidationError as e:
        raise ReviewValidationError(
            f"Schema validation failed: {e.message}"
        )


def main() -> None:
    """CLI entry point for validation.

    Usage:
        python -m cletus_code.validate_json <review.json> [schema.json]
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate review.json against required fields"
    )
    parser.add_argument(
        "review_json",
        type=Path,
        help="Path to review.json file"
    )
    parser.add_argument(
        "schema_json",
        type=Path,
        nargs='?',
        help="Optional path to JSON schema for additional validation"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    try:
        validate_review_json(args.review_json, args.schema_json)
        print(f"✓ Validation passed: {args.review_json}")
        sys.exit(0)
    except ReviewValidationError as e:
        print(f"✗ Validation failed: {e}", file=sys.stderr)
        if e.missing_fields:
            print(f"  Missing fields: {', '.join(e.missing_fields)}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
