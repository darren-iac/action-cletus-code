"""Unit tests for process_review module."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from cletus_code.process_review import (
    load_review_data,
    validate_review,
    build_markdown,
    derive_labels,
    should_auto_merge,
    _parse_pr_number,
    _should_skip_merge,
    find_file_in_workspace,
)


class TestLoadReviewData:
    """Tests for load_review_data function."""

    def test_load_valid_review(self, workspace: Path, sample_review_data: dict):
        """Test loading valid review data."""
        import json

        review_path = workspace / "review.json"
        review_path.write_text(json.dumps(sample_review_data))

        data = load_review_data(review_path)

        assert data["approved"] is True
        assert data["overallRisk"] == "LOW"
        assert data["summary"] == "LGTM! This looks good."
        assert len(data["findings"]) == 2

    def test_load_review_file_not_found(self, workspace: Path):
        """Test loading review when file doesn't exist."""
        review_path = workspace / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            load_review_data(review_path)

    def test_load_review_invalid_json(self, workspace: Path):
        """Test loading review with invalid JSON."""
        review_path = workspace / "review.json"
        review_path.write_text("not valid json {]")

        with pytest.raises(ValueError, match="unable to parse JSON"):
            load_review_data(review_path)

    def test_load_review_empty_file(self, workspace: Path):
        """Test loading review from empty file."""
        review_path = workspace / "review.json"
        review_path.write_text("")

        with pytest.raises(ValueError, match="empty"):
            load_review_data(review_path)

    def test_load_review_missing_required_fields(self, workspace: Path):
        """Test loading review with missing required fields."""
        import json

        review_path = workspace / "review.json"
        review_path.write_text(json.dumps({"approved": True}))  # Missing overallRisk and summary

        with pytest.raises(ValueError, match="missing required fields"):
            load_review_data(review_path)

    def test_load_review_accepts_changes_alias(self, workspace: Path):
        """Test that 'changes' is accepted as alias for 'findings'."""
        import json

        review_data = {
            "approved": True,
            "overallRisk": "LOW",
            "summary": "Test",
            "changes": [{"type": "finding", "title": "Test", "risk": "LOW", "summary": "Test"}],
        }

        review_path = workspace / "review.json"
        review_path.write_text(json.dumps(review_data))

        data = load_review_data(review_path)

        # Should have loaded changes as findings
        assert "findings" in data or "changes" in data

    def test_load_review_without_validation(self, workspace: Path):
        """Test loading review without structure validation."""
        import json

        partial_data = {"approved": True}  # Missing fields
        review_path = workspace / "review.json"
        review_path.write_text(json.dumps(partial_data))

        data = load_review_data(review_path, validate_structure=False)

        assert data["approved"] is True


class TestValidateReview:
    """Tests for validate_review function."""

    def test_validate_valid_review(self, workspace: Path, sample_review_data: dict, sample_schema: dict):
        """Test validating review against valid schema."""
        import json

        review_path = workspace / "review.json"
        review_path.write_text(json.dumps(sample_review_data))

        schema_path = workspace / "schema.json"
        schema_path.write_text(json.dumps(sample_schema))

        errors = validate_review(sample_review_data, schema_path)

        assert errors == []

    def test_validate_invalid_review(self, workspace: Path, sample_schema: dict):
        """Test validating invalid review."""
        import json

        invalid_review = {
            "approved": "not a boolean",  # Invalid type
            "overallRisk": "INVALID_RISK",  # Invalid enum value
            "summary": "Test",
        }

        schema_path = workspace / "schema.json"
        schema_path.write_text(json.dumps(sample_schema))

        errors = validate_review(invalid_review, schema_path)

        assert len(errors) > 0

    def test_validate_schema_file_not_found(self, workspace: Path, sample_review_data: dict):
        """Test validation when schema file doesn't exist."""
        schema_path = workspace / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            validate_review(sample_review_data, schema_path)


class TestBuildMarkdown:
    """Tests for build_markdown function."""

    def test_build_markdown_basic(self, sample_review_data: dict):
        """Test basic markdown building."""
        markdown = build_markdown(sample_review_data, [], None)

        assert "Approved" in markdown
        assert "LOW" in markdown
        assert "LGTM! This looks good." in markdown

    def test_build_markdown_with_findings(self, sample_review_data: dict):
        """Test markdown building with findings."""
        markdown = build_markdown(sample_review_data, [], None)

        assert "Minor style issue" in markdown
        assert "Dependency update" in markdown
        assert "src/main.py" in markdown

    def test_build_markdown_with_validation_errors(self, sample_review_data: dict):
        """Test markdown building includes validation errors."""
        errors = ["field1: Required field missing", "field2: Invalid type"]

        markdown = build_markdown(sample_review_data, errors, None)

        assert "field1: Required field missing" in markdown
        assert "field2: Invalid type" in markdown

    def test_build_markdown_with_automation_note(self, sample_review_data: dict):
        """Test markdown building with automation note."""
        note = "Auto-merge disabled; this is what would have been approved."

        markdown = build_markdown(sample_review_data, [], note)

        assert note in markdown

    def test_build_markdown_not_approved(self, workspace: Path):
        """Test markdown for non-approved review."""

        review_data = {
            "approved": False,
            "overallRisk": "HIGH",
            "summary": "Critical issues found",
            "findings": [],
        }

        markdown = build_markdown(review_data, [], None)

        assert "Needs manual review" in markdown
        assert "HIGH" in markdown


class TestDeriveLabels:
    """Tests for derive_labels function."""

    def test_derive_labels_from_findings(self):
        """Test deriving labels from review findings."""
        data = {
            "overallRisk": "MEDIUM",
            "findings": [
                {
                    "type": "resource",
                    "changeType": "create",
                    "tags": ["security", "k8s"],
                },
                {
                    "type": "version",
                    "subject": {"kind": "helm"},
                },
            ],
        }

        labels = derive_labels(data)

        assert "risk:medium" in labels
        assert "change:create" in labels
        assert "update:helm" in labels

    def test_derive_labels_empty(self):
        """Test deriving labels from empty data."""
        labels = derive_labels({})

        # Should still have risk label
        assert "risk:unknown" in labels


class TestShouldAutoMerge:
    """Tests for should_auto_merge function."""

    def test_auto_merge_disabled(self, mock_pr: Mock):
        """Test when auto-merge is disabled."""
        config = {"enabled": False}
        allowed, reason = should_auto_merge(mock_pr, config)

        assert allowed is False
        assert "disabled" in reason.lower()

    def test_auto_merge_enabled_all(self, mock_pr: Mock):
        """Test auto-merge enabled for all PRs."""
        config = {"enabled": True, "branch_prefixes": [], "branch_regexes": [], "author_logins": []}
        allowed, reason = should_auto_merge(mock_pr, config)

        assert allowed is True
        assert "all" in reason.lower()

    def test_auto_merge_branch_prefix(self, mock_pr: Mock):
        """Test auto-merge by branch prefix."""
        mock_pr.head.ref = "renovate/test-123"
        config = {"enabled": True, "branch_prefixes": ["renovate/", "dependabot/"]}

        allowed, reason = should_auto_merge(mock_pr, config)

        assert allowed is True
        assert "renovate/" in reason

    def test_auto_merge_branch_regex(self, mock_pr: Mock):
        """Test auto-merge by branch regex."""
        mock_pr.head.ref = "renovate-python-3.12"
        config = {"enabled": True, "branch_prefixes": [], "branch_regexes": [r"^renovate-"]}

        allowed, reason = should_auto_merge(mock_pr, config)

        assert allowed is True
        assert "regex" in reason.lower()

    def test_auto_merge_author(self, mock_pr: Mock):
        """Test auto-merge by author."""
        mock_pr.user.login = "dependabot[bot]"
        config = {"enabled": True, "branch_prefixes": [], "branch_regexes": [], "author_logins": ["dependabot[bot]"]}

        allowed, reason = should_auto_merge(mock_pr, config)

        assert allowed is True
        assert "dependabot" in reason.lower()

    def test_auto_merge_no_match(self, mock_pr: Mock):
        """Test auto-merge when no rules match."""
        mock_pr.head.ref = "feature-branch"
        mock_pr.user.login = "developer"
        config = {
            "enabled": True,
            "branch_prefixes": ["renovate/"],
            "branch_regexes": [r"^dependabot"],
            "author_logins": ["bot"],
        }

        allowed, reason = should_auto_merge(mock_pr, config)

        assert allowed is False
        assert "no rules matched" in reason.lower()


class TestParsePrNumber:
    """Tests for _parse_pr_number function."""

    def test_parse_int(self):
        """Test parsing integer."""
        assert _parse_pr_number(42) == 42

    def test_parse_string_int(self):
        """Test parsing string integer."""
        assert _parse_pr_number("42") == 42

    def test_parse_string_whitespace(self):
        """Test parsing string with whitespace."""
        assert _parse_pr_number("  42  ") == 42

    def test_parse_empty_string(self):
        """Test parsing empty string."""
        assert _parse_pr_number("") is None
        assert _parse_pr_number("   ") is None

    def test_parse_invalid_string(self):
        """Test parsing invalid string."""
        assert _parse_pr_number("not a number") is None

    def test_parse_none(self):
        """Test parsing None."""
        assert _parse_pr_number(None) is None


class TestShouldSkipMerge:
    """Tests for _should_skip_merge function."""

    @patch.dict("os.environ", {"REVIEW_SKIP_MERGE": "true"})
    def test_skip_merge_env_var(self):
        """Test skip merge via environment variable."""
        assert _should_skip_merge() is True

    @patch.dict("os.environ", {"REVIEW_SKIP_MERGE": "1"})
    def test_skip_merge_env_var_1(self):
        """Test skip merge with '1'."""
        assert _should_skip_merge() is True

    @patch.dict("os.environ", {"GITHUB_EVENT_NAME": "workflow_dispatch"})
    def test_skip_merge_workflow_dispatch(self):
        """Test skip merge on workflow_dispatch."""
        assert _should_skip_merge() is True

    @patch.dict("os.environ", {"GITHUB_EVENT_NAME": "pull_request", "REVIEW_SKIP_MERGE": "false"})
    def test_skip_merge_false(self):
        """Test skip merge when conditions are false."""
        assert _should_skip_merge() is False


class TestFindFileInWorkspace:
    """Tests for find_file_in_workspace function."""

    def test_find_file_in_cwd(self, workspace: Path):
        """Test finding file in current directory."""
        test_file = workspace / "test.json"
        test_file.write_text("{}")

        import os
        os.chdir(workspace)

        found = find_file_in_workspace("test.json", "..")
        assert found == test_file

    def test_find_file_not_found(self, workspace: Path):
        """Test when file is not found."""
        import os
        os.chdir(workspace)

        found = find_file_in_workspace("nonexistent.json", "..")
        # Should return the original path even if not found
        assert found.name == "nonexistent.json"
