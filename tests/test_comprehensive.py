"""Comprehensive pytest tests for the Temu Claude review workflow.

Tests cover:
- New findings schema (type-based findings)
- Modularized components (config, utils)
- End-to-end workflow scenarios
- Error handling and edge cases
"""

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest


# === Add .github directory to path for proper package imports ===
# We need to add the .github directory (which contains process_review package)
GITHUB_DIR = str(Path(__file__).resolve().parent.parent.parent)
if GITHUB_DIR not in sys.path:
    sys.path.insert(0, GITHUB_DIR)


# === Module Stubs for Testing ===
def setup_module_stubs():
    """Create stub modules for dependencies that may not be installed."""
    # GitHub stub
    try:
        import github
    except ModuleNotFoundError:
        github_module = types.ModuleType("github")
        sys.modules["github"] = github_module

        class _StubGithub:
            def __init__(self, *_, **__):
                pass

        github_module.Github = _StubGithub

        github_exception_module = types.ModuleType("github.GithubException")

        class _StubGithubException(Exception):
            def __init__(self, status, *_, **__):
                super().__init__(status)
                self.status = status

        github_exception_module.GithubException = _StubGithubException
        sys.modules["github.GithubException"] = github_exception_module

        pull_request_module = types.ModuleType("github.PullRequest")
        pull_request_module.PullRequest = lambda: None
        sys.modules["github.PullRequest"] = pull_request_module

        repository_module = types.ModuleType("github.Repository")
        repository_module.Repository = lambda: None
        sys.modules["github.Repository"] = repository_module


setup_module_stubs()

# === Import Process Review Modules ===
# Import as a proper package - this will handle relative imports correctly
# We need to import process_review.process_review to get all internal functions
from process_review import process_review as pr
from process_review import config as config_module
from process_review import utils


# === Test Fixtures ===

@pytest.fixture
def sample_review_new_schema():
    """Sample review data using new unified schema."""
    return {
        "approved": False,
        "overallRisk": "HIGH",
        "summary": "PostgreSQL chart upgrade with FIPS compliance changes",
        "findings": [
            {
                "type": "version",
                "title": "postgresql chart 18.0.15 -> 18.1.4",
                "summary": "Unknown security impact, FIPS mode enabled",
                "risk": "HIGH",
                "tags": ["update:chart"],
                "subject": {
                    "name": "postgresql",
                    "kind": "chart",
                    "from": "18.0.15",
                    "to": "18.1.4"
                },
                "references": [
                    {"url": "https://github.com/bitnami/charts", "note": "Chart repository"}
                ]
            },
            {
                "type": "resource",
                "title": "StatefulSet/rallly/rallly-postgresql",
                "summary": "Added FIPS environment variable",
                "risk": "HIGH",
                "tags": ["change:container"],
                "cosmetic": False,
                "location": {"resource": "StatefulSet/rallly/rallly-postgresql"},
                "evidence": {
                    "diff": "+        - name: OPENSSL_FIPS\n+          value: \"yes\"",
                    "yaml": "environment: OPENSSL_FIPS=yes"
                }
            },
            {
                "type": "resource",
                "title": "Service/rallly/rallly-postgresql-hl",
                "summary": "Removed explicit sessionAffinity",
                "risk": "LOW",
                "tags": ["change:kubernetes"],
                "cosmetic": True,
                "location": {"resource": "Service/rallly/rallly-postgresql-hl"},
                "evidence": {
                    "diff": "-  sessionAffinity: None"
                }
            }
        ]
    }


@pytest.fixture
def minimal_valid_review():
    """Minimal valid review that passes schema validation."""
    return {
        "approved": True,
        "overallRisk": "LOW",
        "summary": "No changes",
        "findings": []
    }


# === Config Tests ===

class TestConfigModule:
    """Tests for config.py module."""

    def test_load_config_returns_expected_structure(self):
        """Test that config loading returns expected keys."""
        cfg = config_module.load_config()
        assert "labels" in cfg
        assert "default_color" in cfg["labels"]
        assert "descriptions" in cfg["labels"]
        assert "change_type_colors" in cfg["labels"]
        assert "risk_colors" in cfg["labels"]
        assert "update_colors" in cfg["labels"]

    def test_get_label_config_with_default(self):
        """Test getting label config with default values."""
        label_config = config_module.get_label_config()
        assert label_config["default_color"] == "6f42c1"
        assert "container" in label_config["change_type_colors"]
        assert "LOW" in label_config["risk_colors"]
        assert "image" in label_config["update_colors"]

    def test_get_label_config_with_custom_config(self):
        """Test getting label config with custom config."""
        custom_config = {
            "labels": {
                "default_color": "ffffff",
                "descriptions": {},
                "change_type_colors": {},
                "risk_colors": {},
                "update_colors": {}
            }
        }
        label_config = config_module.get_label_config(custom_config)
        assert label_config["default_color"] == "ffffff"

    def test_load_review_config_defaults(self, tmp_path, monkeypatch):
        """Test that review config defaults are applied when missing."""
        monkeypatch.chdir(tmp_path)
        cfg = config_module.load_review_config()
        auto_merge = config_module.get_auto_merge_config(cfg)
        assert auto_merge["enabled"] is False
        assert auto_merge["branch_prefixes"] == []

    def test_load_review_config_from_repo_file(self, tmp_path, monkeypatch):
        """Test loading review config from repo .github directory."""
        config_dir = tmp_path / ".github"
        config_dir.mkdir()
        config_path = config_dir / "claude-review.yaml"
        config_path.write_text(
            "auto_merge:\n"
            "  enabled: true\n"
            "  branch_prefixes:\n"
            "    - renovate/\n"
        )
        work_dir = tmp_path / "nested"
        work_dir.mkdir()
        monkeypatch.chdir(work_dir)

        cfg = config_module.load_review_config()
        auto_merge = config_module.get_auto_merge_config(cfg)
        assert auto_merge["enabled"] is True
        assert auto_merge["branch_prefixes"] == ["renovate/"]

    def test_load_review_config_env_override(self, tmp_path, monkeypatch):
        """Test loading review config from explicit env override."""
        config_path = tmp_path / "review.yaml"
        config_path.write_text(
            "auto_merge:\n"
            "  enabled: true\n"
            "  author_logins:\n"
            "    - renovate[bot]\n"
        )
        monkeypatch.setenv("REVIEW_CONFIG_PATH", str(config_path))

        cfg = config_module.load_review_config()
        auto_merge = config_module.get_auto_merge_config(cfg)
        assert auto_merge["enabled"] is True
        assert auto_merge["author_logins"] == ["renovate[bot]"]


# === Utils Tests ===

class TestUtilsModule:
    """Tests for utils.py module."""

    def test_truncate_short_text_unchanged(self):
        """Test that short text is not truncated."""
        assert utils.truncate("hello", limit=10) == "hello"
        assert utils.truncate("hello", limit=5) == "hello"

    def test_truncate_long_text_is_shortened(self):
        """Test that long text is truncated with ellipsis."""
        result = utils.truncate("hello world", limit=8)
        assert result == "hello..."
        assert len(result) == 8

    def test_truncate_handles_none_and_whitespace(self):
        """Test truncate edge cases."""
        assert utils.truncate(None) == ""
        assert utils.truncate("  ") == ""
        assert utils.truncate("  hello  ") == "hello"

    def test_normalize_risk_converts_to_uppercase(self):
        """Test risk normalization."""
        assert utils.normalize_risk("low") == "LOW"
        assert utils.normalize_risk("Medium") == "MEDIUM"
        assert utils.normalize_risk(None) == "UNKNOWN"
        assert utils.normalize_risk("") == "UNKNOWN"

    def test_risk_sort_key_orders_correctly(self):
        """Test that risk sorting puts HIGH first."""
        assert utils.risk_sort_key("HIGH") < utils.risk_sort_key("MEDIUM")
        assert utils.risk_sort_key("MEDIUM") < utils.risk_sort_key("LOW")
        assert utils.risk_sort_key("LOW") < utils.risk_sort_key("UNKNOWN")
        assert utils.risk_sort_key(None) == 3  # UNKNOWN priority

    def test_slugify_creates_url_safe_slugs(self):
        """Test slugify function."""
        assert utils.slugify("Hello World!", "fallback") == "hello-world"
        assert utils.slugify("Test@#$%Name", "fallback") == "test-name"
        assert utils.slugify("", "fallback") == "fallback"
        assert utils.slugify(None, "fallback") == "fallback"

    def test_make_anchor_creates_unique_anchors(self):
        """Test anchor generation with duplicate handling."""
        from collections import defaultdict
        counter = defaultdict(int)

        anchor1 = utils.make_anchor(counter, "version", "nginx 1.25.0", "version")
        assert anchor1 == "version-nginx-1-25-0"

        anchor2 = utils.make_anchor(counter, "version", "nginx 1.25.0", "version")
        assert anchor2 == "version-nginx-1-25-0-1"

        anchor3 = utils.make_anchor(counter, "version", "nginx 1.25.0", "version")
        assert anchor3 == "version-nginx-1-25-0-2"

    def test_format_resource_with_string(self):
        """Test format_resource with string input."""
        assert utils.format_resource("Deployment/default/nginx") == "Deployment/default/nginx"
        assert utils.format_resource("  Deployment/default/nginx  ") == "Deployment/default/nginx"

    def test_format_resource_with_dict(self):
        """Test format_resource with dict input."""
        resource = {
            "kind": "Deployment",
            "namespace": "default",
            "name": "nginx"
        }
        assert utils.format_resource(resource) == "Deployment/default/nginx"

    def test_format_resource_with_cluster_scoped(self):
        """Test format_resource with cluster-scoped resource."""
        resource = {
            "kind": "Namespace",
            "name": "kube-system"
        }
        assert utils.format_resource(resource) == "Namespace/default/kube-system"

    def test_format_resource_with_invalid_input(self):
        """Test format_resource with invalid input."""
        assert utils.format_resource(None) == ""
        assert utils.format_resource(123) == ""
        assert utils.format_resource({}) == "?/default/?"


# === Schema Validation Tests ===

class TestSchemaValidation:
    """Tests for schema validation with new unified schema."""

    def test_load_review_data_with_new_schema(self, tmp_path, sample_review_new_schema):
        """Test loading review data with new unified schema."""
        review_file = tmp_path / "review.json"
        review_file.write_text(json.dumps(sample_review_new_schema))

        data = pr.load_review_data(review_file, validate_structure=False)
        assert data["approved"] == False
        assert data["overallRisk"] == "HIGH"
        assert len(data["findings"]) == 3

    def test_load_review_data_validates_required_fields(self, tmp_path):
        """Test that missing required fields are detected."""
        invalid_review = {
            "approved": True
            # Missing: overallRisk, summary, findings
        }
        review_file = tmp_path / "review.json"
        review_file.write_text(json.dumps(invalid_review))

        with pytest.raises(ValueError, match="missing required fields"):
            pr.load_review_data(review_file, validate_structure=True)

    def test_validate_review_against_real_schema(self, tmp_path, sample_review_new_schema):
        """Test validation against the actual schema file."""
        schema_path = Path(__file__).resolve().parents[2] / "workflows" / "temu-claude-review.schema.json"

        if not schema_path.exists():
            pytest.skip("Schema file not found")

        review_file = tmp_path / "review.json"
        review_file.write_text(json.dumps(sample_review_new_schema))

        data = pr.load_review_data(review_file)
        errors = pr.validate_review(data, schema_path)

        # Should have no validation errors for valid data
        assert errors == []

    def test_validate_detects_invalid_risk_value(self, tmp_path):
        """Test that invalid risk values are caught."""
        invalid_review = {
            "approved": True,
            "overallRisk": "INVALID",  # Should be LOW/MEDIUM/HIGH
            "summary": "Test",
            "findings": []
        }
        review_file = tmp_path / "review.json"
        review_file.write_text(json.dumps(invalid_review))

        data = pr.load_review_data(review_file, validate_structure=False)

        schema_path = Path(__file__).resolve().parents[2] / "workflows" / "temu-claude-review.schema.json"
        if not schema_path.exists():
            pytest.skip("Schema file not found")

        errors = pr.validate_review(data, schema_path)
        # Should have errors about enum constraint
        assert len(errors) > 0


# === Label Derivation Tests ===

class TestLabelDerivation:
    """Tests for label derivation with new schema."""

    def test_derive_labels_with_new_schema(self, sample_review_new_schema):
        """Test label derivation with new unified schema."""
        labels = pr.derive_labels(sample_review_new_schema)

        # Should have change type labels
        assert "change:container" in labels
        assert "change:kubernetes" in labels

        # Should have update kind label
        assert "update:chart" in labels

        # Should have risk label
        assert "risk:high" in labels

    def test_derive_labels_uses_config_colors(self, sample_review_new_schema):
        """Test that derived labels use colors from config."""
        labels = pr.derive_labels(sample_review_new_schema)

        cfg = config_module.get_label_config()
        assert labels["change:container"] == cfg["change_type_colors"]["container"]
        assert labels["update:chart"] == cfg["update_colors"]["chart"]
        assert labels["risk:high"] == cfg["risk_colors"]["HIGH"]


# === Markdown Building Tests ===

class TestMarkdownBuilding:
    """Tests for markdown generation with new schema."""

    def test_build_markdown_with_new_schema(self, sample_review_new_schema, monkeypatch):
        """Test markdown building with new unified schema."""
        captured = {}

        class FakeTemplate:
            def render(self, **context):
                captured.update(context)
                return "Rendered markdown"

        monkeypatch.setattr(pr, "get_template", lambda: FakeTemplate())

        markdown = pr.build_markdown(sample_review_new_schema, [])

        assert markdown.strip() == "Rendered markdown"
        assert captured["verdict"] == "Needs manual review"
        assert captured["overall_risk"] == "HIGH"
        assert len(captured["finding_groups"]) == 2

    def test_version_changes_processed_correctly(self, sample_review_new_schema, monkeypatch):
        """Test that version findings are processed with new schema structure."""
        captured = {}

        class FakeTemplate:
            def render(self, **context):
                captured.update(context)
                return ""

        monkeypatch.setattr(pr, "get_template", lambda: FakeTemplate())

        pr.build_markdown(sample_review_new_schema, [])

        version_group = next(group for group in captured["finding_groups"] if group["type"] == "version")
        assert len(version_group["findings"]) == 1
        finding = version_group["findings"][0]
        assert finding["title"].startswith("postgresql")
        assert finding["subject"]["name"] == "postgresql"
        assert finding["subject"]["kind"] == "chart"
        assert finding["subject"]["from"] == "18.0.15"
        assert finding["subject"]["to"] == "18.1.4"
        assert "update:chart" in finding["tags"]
        assert len(finding["references"]) == 1

    def test_resource_changes_formatted_correctly(self, sample_review_new_schema, monkeypatch):
        """Test that resource findings are normalized correctly."""
        captured = {}

        class FakeTemplate:
            def render(self, **context):
                captured.update(context)
                return ""

        monkeypatch.setattr(pr, "get_template", lambda: FakeTemplate())

        pr.build_markdown(sample_review_new_schema, [])

        resource_group = next(group for group in captured["finding_groups"] if group["type"] == "resource")
        resource_changes = resource_group["findings"]
        assert len(resource_changes) == 2

        # Check StatefulSet resource
        statefulset = next(r for r in resource_changes if "StatefulSet" in r["title"])
        assert statefulset["location"]["resource"] == "StatefulSet/rallly/rallly-postgresql"
        assert "change:container" in statefulset["tags"]
        assert statefulset["risk"] == "HIGH"
        assert statefulset["cosmetic"] is False
        assert len(statefulset["diff"]) > 0

        # Check Service resource
        service = next(r for r in resource_changes if "Service" in r["title"])
        assert service["cosmetic"] is True
        assert service["risk"] == "LOW"


# === Integration Tests ===

class TestIntegrationScenarios:
    """End-to-end integration tests."""

    def test_full_workflow_with_approved_review(self, monkeypatch, tmp_path, minimal_valid_review):
        """Test full workflow when review is approved."""
        monkeypatch.chdir(tmp_path)

        # Create required files
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "review.json").write_text(json.dumps(minimal_valid_review))

        schema_path = Path(__file__).resolve().parents[2] / "workflows" / "temu-claude-review.schema.json"
        if not schema_path.exists():
            (tmp_path / "schema.json").write_text('{"type": "object"}')
            schema_path = tmp_path / "schema.json"

        # Track calls
        calls = []

        class FakeLabel:
            def __init__(self, name):
                self.name = name

        class FakePR:
            def __init__(self):
                self.base = SimpleNamespace(repo=None)  # Will be set to FakeRepo
                self.head = SimpleNamespace(repo=None, ref="branch")
                self.labels_added = []
                self.comments = []
                self.reviews = []
                self._merged = False

            def add_to_labels(self, *labels):
                self.labels_added.extend(labels)

            def create_issue_comment(self, body):
                self.comments.append(body)

            def create_review(self, body, event):
                self.reviews.append((body, event))

            def is_merged(self):
                return self._merged

            def merge(self, merge_method):
                self._merged = True
                return SimpleNamespace(sha="abc123")

        class FakeRepo:
            def __init__(self):
                self.full_name = "test/repo"

            def get_labels(self):
                return []

            def create_label(self, name, color, description):
                # Simulate label already exists (HTTP 422)
                from github.GithubException import GithubException
                raise GithubException(422, f"Label {name} already exists")

            def get_git_ref(self, ref):
                class FakeRef:
                    def delete(self):
                        pass
                return FakeRef()

        fake_pr = FakePR()
        fake_pr.base.repo = FakeRepo()

        def fake_load_pr(token):
            calls.append("load_pr")
            return fake_pr

        monkeypatch.setattr(pr, "load_pull_request", fake_load_pr)
        monkeypatch.setattr(pr, "should_auto_merge", lambda pr_obj, cfg: (True, "enabled"))
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_REPOSITORY", "test/repo")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "event.json"))

        # Run main
        pr.main(["--output-dir", "output", "--schema-file", str(schema_path)])

        # Verify workflow
        assert "load_pr" in calls
        assert len(fake_pr.labels_added) > 0
        assert len(fake_pr.comments) > 0
        assert fake_pr._merged is True  # Should merge when approved

    def test_full_workflow_with_rejected_review(self, monkeypatch, tmp_path, sample_review_new_schema):
        """Test full workflow when review is rejected."""
        monkeypatch.chdir(tmp_path)

        # Create required files
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "review.json").write_text(json.dumps(sample_review_new_schema))

        schema_path = Path(__file__).resolve().parents[2] / "workflows" / "temu-claude-review.schema.json"
        if not schema_path.exists():
            (tmp_path / "schema.json").write_text('{"type": "object"}')
            schema_path = tmp_path / "schema.json"

        # Track calls
        merge_called = []

        class FakePR:
            def __init__(self):
                self.base = SimpleNamespace(repo=None)  # Will be set to FakeRepo
                self.labels_added = []
                self.comments = []

            def add_to_labels(self, *labels):
                self.labels_added.extend(labels)

            def create_issue_comment(self, body):
                self.comments.append(body)

            def merge(self, *args):
                merge_called.append(True)

        class FakeRepo:
            def __init__(self):
                self.full_name = "test/repo"

            def get_labels(self):
                return []

            def create_label(self, name, color, description):
                # Simulate label already exists (HTTP 422)
                from github.GithubException import GithubException
                raise GithubException(422, f"Label {name} already exists")

            def get_git_ref(self, ref):
                class FakeRef:
                    def delete(self):
                        pass
                return FakeRef()

        fake_pr = FakePR()
        fake_pr.base.repo = FakeRepo()

        def fake_load_pr(token):
            return fake_pr

        monkeypatch.setattr(pr, "load_pull_request", fake_load_pr)
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_REPOSITORY", "test/repo")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "event.json"))

        # Run main
        pr.main(["--output-dir", "output", "--schema-file", str(schema_path)])

        # Verify workflow
        assert len(merge_called) == 0  # Should NOT merge when not approved


# === Error Handling Tests ===

class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_handles_missing_review_file(self, tmp_path):
        """Test handling of missing review.json file."""
        missing_file = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            pr.load_review_data(missing_file)

    def test_handles_invalid_json(self, tmp_path):
        """Test handling of invalid JSON."""
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("not json")

        with pytest.raises(ValueError, match="unable to parse JSON"):
            pr.load_review_data(invalid_file)

    def test_handles_empty_review_file(self, tmp_path):
        """Test handling of empty review file."""
        empty_file = tmp_path / "empty.json"
        empty_file.write_text("")

        with pytest.raises(ValueError, match="empty"):
            pr.load_review_data(empty_file)
