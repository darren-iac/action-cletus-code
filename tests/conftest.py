"""Shared pytest fixtures and configuration."""

import json
from pathlib import Path
from unittest.mock import Mock
from typing import Any

import pytest
from _pytest.monkeypatch import MonkeyPatch

from github import Github
from github.PullRequest import PullRequest
from github.Repository import Repository


@pytest.fixture
def github_token() -> str:
    """Fake GitHub token for testing."""
    return "ghp_test_token_1234567890"


@pytest.fixture
def repository() -> str:
    """Test repository name."""
    return "test-owner/test-repo"


@pytest.fixture
def pr_number() -> int:
    """Test PR number."""
    return 42


@pytest.fixture
def mock_repo(repository: str) -> Mock:
    """Mock GitHub Repository object."""
    repo = Mock(spec=Repository)
    repo.full_name = repository
    repo.owner = Mock()
    repo.owner.login = "test-owner"
    repo.name = "test-repo"
    return repo


@pytest.fixture
def mock_pr(mock_repo: Mock, pr_number: int) -> Mock:
    """Mock GitHub PullRequest object."""
    pr = Mock(spec=PullRequest)
    pr.number = pr_number
    pr.title = "Test PR"
    pr.body = "Test PR body"
    pr.state = "open"
    pr.mergeable = True
    pr.mergeable_state = "clean"
    pr.is_merged.return_value = False

    pr.head = Mock()
    pr.head.ref = "feature-branch"
    pr.head.sha = "abc123def456"
    pr.head.repo = mock_repo

    pr.base = Mock()
    pr.base.ref = "main"
    pr.base.sha = "def456abc123"
    pr.base.repo = mock_repo

    pr.user = Mock()
    pr.user.login = "test-user"

    pr.repo = mock_repo

    return pr


@pytest.fixture
def mock_github(mock_repo: Mock, mock_pr: Mock) -> Mock:
    """Mock Github client."""
    gh = Mock(spec=Github)
    gh.get_repo.return_value = mock_repo
    mock_repo.get_pull.return_value = mock_pr
    mock_repo.get_labels.return_value = []
    return gh


@pytest.fixture
def sample_review_data() -> dict[str, Any]:
    """Sample review data for testing."""
    return {
        "approved": True,
        "overallRisk": "LOW",
        "summary": "LGTM! This looks good.",
        "findings": [
            {
                "type": "finding",
                "title": "Minor style issue",
                "risk": "LOW",
                "summary": "Consider using f-string instead of format()",
                "location": {
                    "path": "src/main.py",
                    "line": 42,
                },
                "tags": ["style", "python"],
                "cosmetic": True,
                "evidence": {
                    "snippet": 'message = "Hello {}".format(name)',
                },
            },
            {
                "type": "version",
                "title": "Dependency update",
                "risk": "MEDIUM",
                "summary": "Python version bumped from 3.11 to 3.12",
                "subject": {
                    "kind": "python",
                    "name": "python",
                    "from": "3.11",
                    "to": "3.12",
                },
                "tags": ["update:python", "dependencies"],
                "cosmetic": False,
            },
        ],
    }


@pytest.fixture
def sample_review_json(sample_review_data: dict[str, Any]) -> str:
    """Sample review JSON string."""
    return json.dumps(sample_review_data, indent=2)


@pytest.fixture
def sample_schema() -> dict[str, Any]:
    """Sample JSON schema for review validation."""
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["approved", "overallRisk", "summary"],
        "properties": {
            "approved": {"type": "boolean"},
            "overallRisk": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "UNKNOWN"]},
            "summary": {"type": "string"},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["type", "title", "risk", "summary"],
                    "properties": {
                        "type": {"type": "string"},
                        "title": {"type": "string"},
                        "risk": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
                        "summary": {"type": "string"},
                        "location": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "line": {"type": "integer"},
                            },
                        },
                    },
                },
            },
        },
    }


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace directory structure."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create common directories
    (workspace / "pull-request").mkdir()
    (workspace / "main").mkdir()
    (workspace / "output").mkdir()

    return workspace


@pytest.fixture
def mock_env(monkeypatch: MonkeyPatch, github_token: str, repository: str, workspace: Path) -> None:
    """Set up mock environment variables."""
    monkeypatch.setenv("GITHUB_TOKEN", github_token)
    monkeypatch.setenv("GITHUB_REPOSITORY", repository)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/42/merge")
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(workspace / "event.json"))


@pytest.fixture
def sample_changed_files() -> list[str]:
    """Sample changed files list."""
    return [
        "src/main.py",
        "src/utils.py",
        "k8s/deployment.yaml",
        "k8s/kustomization.yaml",
    ]


@pytest.fixture
def mock_kustomize_files(workspace: Path) -> None:
    """Create sample kustomize files in the workspace."""
    # Create kustomization.yaml in PR directory
    kustomize_dir = workspace / "pull-request" / "k8s"
    kustomize_dir.mkdir(parents=True, exist_ok=True)

    (kustomize_dir / "kustomization.yaml").write_text("""
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
""")

    (kustomize_dir / "deployment.yaml").write_text("""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-app
spec:
  replicas: 3
""")

    # Create similar in base directory
    base_kustomize_dir = workspace / "main" / "k8s"
    base_kustomize_dir.mkdir(parents=True, exist_ok=True)

    (base_kustomize_dir / "kustomization.yaml").write_text("""
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
""")

    (base_kustomize_dir / "deployment.yaml").write_text("""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-app
spec:
  replicas: 2
""")


@pytest.fixture
def mock_event_payload(workspace: Path, pr_number: int) -> None:
    """Create a sample GitHub event payload."""
    event = {
        "number": pr_number,
        "pull_request": {
            "number": pr_number,
            "title": "Test PR",
            "state": "open",
            "user": {"login": "test-user"},
            "base": {
                "ref": "main",
                "sha": "def456abc123",
            },
            "head": {
                "ref": "feature-branch",
                "sha": "abc123def456",
            },
        },
    }

    event_path = workspace / "event.json"
    event_path.write_text(json.dumps(event))
