"""Unit tests for the review orchestrator."""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from typing import Any

import pytest

from cletus_code.run_review import ReviewOrchestrator
from cletus_code.plugins.base import PluginResult


class TestReviewOrchestrator:
    """Tests for ReviewOrchestrator."""

    @patch("cletus_code.run_review.Github")
    def test_init(
        self,
        mock_github: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        sample_changed_files: list[str],
        monkeypatch,
    ):
        """Test orchestrator initialization."""
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)

        # Mock the Github client
        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_github.return_value.get_repo.return_value = mock_repo

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=sample_changed_files,
            workspace_root=workspace,
            skill_name="test-skill",
            output_dir=workspace / "output",
        )

        assert orchestrator.github_token == github_token
        assert orchestrator.changed_files == sample_changed_files
        assert orchestrator.workspace_root == workspace
        assert orchestrator.output_dir == workspace / "output"
        assert orchestrator.skill_name == "test-skill"
        assert orchestrator.repository == repository
        assert len(orchestrator.plugins) > 0

    @patch("cletus_code.run_review.Github")
    def test_init_default_values(
        self,
        mock_github: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        monkeypatch,
    ):
        """Test orchestrator initialization with default values."""
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)

        # Mock the Github client
        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_github.return_value.get_repo.return_value = mock_repo

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=["test.py"],
        )

        assert orchestrator.workspace_root == Path.cwd()
        assert orchestrator.output_dir == Path.cwd() / "output"
        assert orchestrator.skill_name is None
        assert orchestrator.pr_dir == Path.cwd() / "pull-request"
        assert orchestrator.base_dir == Path.cwd() / "main"

    def test_init_raises_without_repository(self, workspace: Path):
        """Test that initialization fails when GITHUB_REPOSITORY is not set."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="GITHUB_REPOSITORY"):
                ReviewOrchestrator(
                    github_token="test-token",
                    changed_files=["test.py"],
                    workspace_root=workspace,
                )

    @patch("cletus_code.run_review.Github")
    def test_setup_pr_context_for_pull_request_event(
        self,
        mock_github: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        mock_env: None,
        mock_event_payload: None,
    ):
        """Test PR context setup for pull_request event."""
        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=[],
            workspace_root=workspace,
        )

        context = orchestrator._setup_pr_context()

        assert context["pr_number"] == 42
        assert context["base_sha"] == "def456abc123"
        assert context["head_sha"] == "abc123def456"
        assert context["event_name"] == "pull_request"

    @patch("cletus_code.run_review._resolve_pr_number")
    @patch("cletus_code.run_review.get_pull_request_context")
    @patch("cletus_code.run_review.resolve_rebase_refs")
    @patch("cletus_code.run_review.Github")
    def test_setup_pr_context_for_workflow_dispatch(
        self,
        mock_github: Mock,
        mock_resolve_refs: Mock,
        mock_get_context: Mock,
        mock_resolve_pr: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        monkeypatch,
    ):
        """Test PR context setup for workflow_dispatch event."""
        monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)

        # Mock Github client to avoid API call
        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_github.return_value.get_repo.return_value = mock_repo

        mock_resolve_pr.return_value = 42
        mock_get_context.return_value = {
            "pr_number": 42,
            "base_sha": "base123",
            "head_sha": "head456",
            "merge_sha": "merge789",
        }
        mock_resolve_refs.return_value = ("resolved_base", "resolved_head")

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=[],
            workspace_root=workspace,
        )

        context = orchestrator._setup_pr_context()

        assert context["pr_number"] == 42
        assert context["base_sha"] == "resolved_base"
        assert context["head_sha"] == "resolved_head"
        assert context["event_name"] == "workflow_dispatch"

    @patch("cletus_code.run_review.subprocess.run")
    @patch("cletus_code.run_review.Github")
    def test_checkout_branches(
        self,
        mock_github: Mock,
        mock_subprocess: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        monkeypatch,
    ):
        """Test branch checkout process."""
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)
        mock_subprocess.return_value = Mock(returncode=0)
        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_github.return_value.get_repo.return_value = mock_repo

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=[],
            workspace_root=workspace,
        )

        pr_context = {
            "pr_number": 42,
            "base_sha": "base123",
            "head_sha": "head456",
        }

        orchestrator._checkout_branches(pr_context)

        # Verify directories were created
        assert orchestrator.pr_dir.exists()
        assert orchestrator.base_dir.exists()

        # Verify git commands were called
        assert mock_subprocess.call_count >= 6  # init, remote, fetch, checkout for each branch

    @patch("cletus_code.run_review.subprocess.run")
    @patch("cletus_code.run_review.Github")
    def test_checkout_branches_creates_directories(
        self,
        mock_github: Mock,
        mock_subprocess: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        monkeypatch,
    ):
        """Test that checkout creates directories if they don't exist."""
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)
        mock_subprocess.return_value = Mock(returncode=0)
        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_github.return_value.get_repo.return_value = mock_repo

        # Remove the directories created by fixture
        pr_dir = workspace / "pull-request"
        base_dir = workspace / "main"
        if pr_dir.exists():
            pr_dir.rmdir()
        if base_dir.exists():
            base_dir.rmdir()

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=[],
            workspace_root=workspace,
        )

        pr_context = {
            "pr_number": 42,
            "base_sha": "base123",
            "head_sha": "head456",
        }

        orchestrator._checkout_branches(pr_context)

        # Verify directories were created
        assert pr_dir.exists()
        assert base_dir.exists()

    @patch("cletus_code.run_review.Github")
    def test_run_plugins(
        self,
        mock_github: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        mock_pr: Mock,
        monkeypatch,
    ):
        """Test running plugins."""
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)
        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_github.return_value.get_repo.return_value = mock_repo

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=[],
            workspace_root=workspace,
        )

        # Mock the plugin to detect and execute
        mock_plugin = Mock()
        mock_plugin.name = "test-plugin"
        mock_plugin.detects.return_value = True
        mock_plugin.execute.return_value = PluginResult(
            success=True,
            message="Test plugin executed",
        )

        orchestrator.plugins = [mock_plugin]

        results = orchestrator._run_plugins(mock_pr)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].message == "Test plugin executed"

        # Verify plugin was called
        mock_plugin.detects.assert_called_once()
        mock_plugin.execute.assert_called_once()

    @patch("cletus_code.run_review.Github")
    def test_run_plugins_skips_non_detecting(
        self,
        mock_github: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        mock_pr: Mock,
        monkeypatch,
    ):
        """Test that plugins that don't detect are skipped."""
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)
        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_github.return_value.get_repo.return_value = mock_repo

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=[],
            workspace_root=workspace,
        )

        mock_plugin = Mock()
        mock_plugin.name = "test-plugin"
        mock_plugin.detects.return_value = False

        orchestrator.plugins = [mock_plugin]

        results = orchestrator._run_plugins(mock_pr)

        assert len(results) == 0
        mock_plugin.detects.assert_called_once()
        mock_plugin.execute.assert_not_called()

    @patch("cletus_code.run_review.Github")
    def test_run_plugins_handles_exceptions(
        self,
        mock_github: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        mock_pr: Mock,
        monkeypatch,
    ):
        """Test that plugin exceptions are handled gracefully."""
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)
        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_github.return_value.get_repo.return_value = mock_repo

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=[],
            workspace_root=workspace,
        )

        mock_plugin = Mock()
        mock_plugin.name = "failing-plugin"
        mock_plugin.detects.return_value = True
        mock_plugin.execute.side_effect = Exception("Plugin failed!")

        orchestrator.plugins = [mock_plugin]

        results = orchestrator._run_plugins(mock_pr)

        assert len(results) == 1
        assert results[0].success is False
        assert "failed" in results[0].message.lower()

    @patch("cletus_code.run_review.Github")
    def test_build_claude_prompt(
        self,
        mock_github: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        monkeypatch,
    ):
        """Test building Claude Code prompt."""
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)
        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_github.return_value.get_repo.return_value = mock_repo

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=[],
            workspace_root=workspace,
        )

        skill = "# Test Skill\nReview this code."
        plugin_results = [
            PluginResult(
                success=True,
                message="Plugin executed",
                review_context="## Plugin Context\nAdditional info.",
            )
        ]

        prompt = orchestrator._build_claude_prompt(skill, plugin_results)

        assert skill in prompt
        assert "## Plugin Context" in prompt
        assert "Additional info." in prompt

    @patch("cletus_code.run_review.Github")
    def test_build_claude_prompt_without_plugins(
        self,
        mock_github: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        monkeypatch,
    ):
        """Test building prompt without plugin results."""
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)
        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_github.return_value.get_repo.return_value = mock_repo

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=[],
            workspace_root=workspace,
        )

        skill = "# Test Skill"
        prompt = orchestrator._build_claude_prompt(skill, [])

        assert prompt == skill

    @patch("cletus_code.run_review.Github")
    def test_invoke_claude_code_writes_prompt_file(
        self,
        mock_github: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        monkeypatch,
    ):
        """Test that Claude Code invocation writes prompt file."""
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)
        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_github.return_value.get_repo.return_value = mock_repo

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=[],
            workspace_root=workspace,
        )

        prompt = "# Test Prompt\nReview this."

        orchestrator._invoke_claude_code(prompt)

        prompt_file = orchestrator.output_dir / "claude-prompt.md"
        assert prompt_file.exists()
        assert prompt_file.read_text() == prompt

    @patch("cletus_code.run_review.Github")
    def test_find_schema_file(
        self,
        mock_github: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        monkeypatch,
    ):
        """Test finding schema file in workspace."""
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)
        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_github.return_value.get_repo.return_value = mock_repo

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=[],
            workspace_root=workspace,
        )

        # Create a schema file
        schema_path = workspace / ".github" / "workflows" / "temu-claude-review.schema.json"
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text("{}")

        found = orchestrator._find_schema_file()

        assert found == schema_path

    @patch("cletus_code.run_review.Github")
    def test_find_schema_file_returns_none_when_not_found(
        self,
        mock_github: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        monkeypatch,
    ):
        """Test schema file search when none exists."""
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)
        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_github.return_value.get_repo.return_value = mock_repo

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=[],
            workspace_root=workspace,
        )

        found = orchestrator._find_schema_file()

        assert found is None

    @patch("cletus_code.run_review.publish_comment")
    @patch("cletus_code.run_review.Github")
    def test_post_comment(
        self,
        mock_github: Mock,
        mock_publish: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        mock_pr: Mock,
        monkeypatch,
    ):
        """Test posting a plugin comment."""
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)
        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_github.return_value.get_repo.return_value = mock_repo

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=[],
            workspace_root=workspace,
        )

        content = "## Test Comment\nThis is a test."
        orchestrator._post_comment(mock_pr, content)

        mock_pr.create_issue_comment.assert_called_once_with(content)

    @patch("cletus_code.run_review.apply_labels")
    @patch("cletus_code.run_review.Github")
    def test_derive_labels(
        self,
        mock_github: Mock,
        mock_apply: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        sample_review_data: dict,
        monkeypatch,
    ):
        """Test deriving labels from review data."""
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)
        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_github.return_value.get_repo.return_value = mock_repo

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=[],
            workspace_root=workspace,
        )

        labels = orchestrator._derive_labels(sample_review_data)

        assert isinstance(labels, dict)
        # Should have risk label
        assert "risk:low" in labels

    @patch("cletus_code.run_review.Github")
    def test_derive_labels_empty(
        self,
        mock_github: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        monkeypatch,
    ):
        """Test deriving labels from empty review data."""
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)
        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_github.return_value.get_repo.return_value = mock_repo

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=[],
            workspace_root=workspace,
        )

        labels = orchestrator._derive_labels({})

        assert isinstance(labels, dict)
