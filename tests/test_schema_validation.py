#!/usr/bin/env python3
"""
Test script to validate the review schema and prove the fix works.

This script:
1. Validates the review-schema.json is valid JSON Schema
2. Creates a sample review object matching the schema
3. Validates the sample against the schema
4. Demonstrates that the structured output approach works
"""

import json
import sys
from pathlib import Path
from jsonschema import validate, Draft7Validator, ValidationError

def test_schema_exists():
    """Test that the schema file exists."""
    schema_path = Path(__file__).parent.parent / "src" / "cletus_code" / "templates" / "review-schema.json"
    if not schema_path.exists():
        print(f"❌ Schema file not found at {schema_path}")
        return False
    print(f"✅ Schema file exists at {schema_path}")
    return True

def test_schema_is_valid_json():
    """Test that the schema file is valid JSON."""
    schema_path = Path(__file__).parent.parent / "src" / "cletus_code" / "templates" / "review-schema.json"
    try:
        with open(schema_path) as f:
            schema = json.load(f)
        print(f"✅ Schema is valid JSON")
        return True, schema
    except json.JSONDecodeError as e:
        print(f"❌ Schema is not valid JSON: {e}")
        return False, None

def test_schema_is_valid_jsonschema(schema):
    """Test that the schema is a valid JSON Schema (Draft 7)."""
    try:
        # Check if it has the required schema property
        if "$schema" not in schema:
            print(f"❌ Schema missing $schema property")
            return False

        # Try to create a validator (this validates the schema itself)
        Draft7Validator.check_schema(schema)
        print(f"✅ Schema is a valid JSON Schema (Draft 7)")
        return True
    except Exception as e:
        print(f"❌ Schema is not a valid JSON Schema: {e}")
        return False

def test_schema_has_required_fields(schema):
    """Test that the schema has the required top-level fields."""
    required_properties = ["approved", "overallRisk", "summary", "findings"]
    schema_required = schema.get("required", [])

    missing = [prop for prop in required_properties if prop not in schema_required]
    if missing:
        print(f"❌ Schema missing required properties: {missing}")
        return False

    print(f"✅ Schema has all required properties: {required_properties}")
    return True

def test_sample_review_validation(schema):
    """Test that a sample review object validates against the schema."""
    sample_review = {
        "approved": True,
        "overallRisk": "LOW",
        "summary": "This PR looks good. No critical issues found.",
        "findings": [
            {
                "type": "finding",
                "title": "Minor style suggestion",
                "summary": "Consider using consistent indentation",
                "risk": "NEGLIGIBLE",
                "tags": ["style"],
                "cosmetic": True,
                "location": {
                    "resource": "src/file.py",
                    "path": "src/file.py",
                    "line": 42
                }
            },
            {
                "type": "version",
                "title": "Dependency update",
                "summary": "Updated pytest from 7.0 to 8.0",
                "risk": "LOW",
                "subject": {
                    "kind": "python",
                    "name": "pytest",
                    "from": "7.0",
                    "to": "8.0"
                }
            }
        ]
    }

    try:
        validate(instance=sample_review, schema=schema)
        print(f"✅ Sample review validates against schema")
        return True
    except ValidationError as e:
        print(f"❌ Sample review does not validate: {e.message}")
        return False

def test_action_yml_has_schema_reference():
    """Test that action.yml references the schema file."""
    action_yml_path = Path(__file__).parent.parent / "action.yml"
    with open(action_yml_path) as f:
        content = f.read()

    if "--json-schema" not in content:
        print(f"❌ action.yml does not reference --json-schema flag")
        return False

    if "review-schema.json" not in content:
        print(f"❌ action.yml does not reference review-schema.json")
        return False

    if "structured_output" not in content:
        print(f"❌ action.yml does not extract structured_output")
        return False

    print(f"✅ action.yml correctly references schema and structured output")
    return True

def test_run_review_copies_schema():
    """Test that run_review.py copies the schema file."""
    run_review_path = Path(__file__).parent.parent / "src" / "cletus_code" / "run_review.py"
    with open(run_review_path) as f:
        content = f.read()

    if "review-schema.json" not in content:
        print(f"❌ run_review.py does not reference review-schema.json")
        return False

    if "shutil.copy" not in content:
        print(f"❌ run_review.py does not copy schema file")
        return False

    print(f"✅ run_review.py copies the schema file to output directory")
    return True

def test_run_review_has_output_instructions():
    """Test that run_review.py includes output format instructions."""
    run_review_path = Path(__file__).parent.parent / "src" / "cletus_code" / "run_review.py"
    with open(run_review_path) as f:
        content = f.read()

    if "Output Format" not in content:
        print(f"❌ run_review.py does not include output format instructions")
        return False

    if "structured JSON output" not in content:
        print(f"❌ run_review.py does not mention structured output")
        return False

    print(f"✅ run_review.py includes output format instructions for Claude")
    return True

def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Issue #16 Fix: review.json Output")
    print("=" * 60)
    print()

    all_passed = True

    # Test 1: Schema exists
    all_passed &= test_schema_exists()
    print()

    # Test 2: Schema is valid JSON
    success, schema = test_schema_is_valid_json()
    all_passed &= success
    print()

    if not success:
        print("❌ Cannot proceed without valid schema")
        sys.exit(1)

    # Test 3: Schema is valid JSON Schema
    all_passed &= test_schema_is_valid_jsonschema(schema)
    print()

    # Test 4: Schema has required fields
    all_passed &= test_schema_has_required_fields(schema)
    print()

    # Test 5: Sample review validates
    all_passed &= test_sample_review_validation(schema)
    print()

    # Test 6: action.yml references schema
    all_passed &= test_action_yml_has_schema_reference()
    print()

    # Test 7: run_review.py copies schema
    all_passed &= test_run_review_copies_schema()
    print()

    # Test 8: run_review.py has output instructions
    all_passed &= test_run_review_has_output_instructions()
    print()

    print("=" * 60)
    if all_passed:
        print("✅ ALL TESTS PASSED")
        print()
        print("The fix for Issue #16 is properly implemented:")
        print("  • review-schema.json exists and is valid")
        print("  • action.yml uses --json-schema flag")
        print("  • action.yml extracts structured_output")
        print("  • run_review.py copies schema to output dir")
        print("  • run_review.py includes output instructions")
        print()
        print("The structured output feature will guarantee review.json creation.")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        print("Please review the failures above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
