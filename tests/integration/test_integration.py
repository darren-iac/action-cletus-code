"""Integration tests for the review workflow."""

from pathlib import Path
from unittest.mock import Mock, patch
import json


from cletus_code.run_review import ReviewOrchestrator
from cletus_code.process_review import load_review_data, build_markdown


class TestReviewWorkflow:
    """Integration tests for the complete review workflow."""

    @patch("cletus_code.run_review.subprocess.run")
    @patch("cletus_code.run_review.Github")
    def test_full_review_workflow(
        self,
        mock_github: Mock,
        mock_subprocess: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        sample_changed_files: list[str],
        mock_env: None,
        mock_event_payload: None,
    ):
        """Test the complete review workflow from start to finish."""
        # Setup mocks
        mock_subprocess.return_value = Mock(returncode=0, stdout="", stderr="")

        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_pr = Mock()
        mock_pr.number = 42
        mock_pr.title = "Test PR"
        mock_pr.head.ref = "feature-branch"
        mock_pr.head.sha = "abc123"
        mock_pr.base.ref = "main"
        mock_pr.base.sha = "def456"
        mock_pr.user.login = "test-user"
        mock_pr.is_merged.return_value = False

        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_labels.return_value = []
        mock_github.return_value.get_repo.return_value = mock_repo

        # Create review.json in output (simulating Claude Code output)
        review_data = {
            "approved": True,
            "overallRisk": "LOW",
            "summary": "LGTM! No issues found.",
            "findings": [
                {
                    "type": "finding",
                    "title": "Minor suggestion",
                    "risk": "LOW",
                    "summary": "Consider using type hints",
                    "tags": ["style"],
                    "cosmetic": True,
                }
            ],
        }

        output_dir = workspace / "output"
        output_dir.mkdir(exist_ok=True)
        (output_dir / "review.json").write_text(json.dumps(review_data))

        # Run orchestrator
        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=sample_changed_files,
            workspace_root=workspace,
        )

        with patch.object(orchestrator, "_invoke_claude_code"):
            with patch.object(orchestrator, "_post_comment"):
                orchestrator.run()

        # Verify review was processed
        review_md = output_dir / "review.md"
        assert review_md.exists()
        markdown = review_md.read_text()
        assert "LGTM!" in markdown
        assert "Approved" in markdown

    @patch("cletus_code.run_review.subprocess.run")
    @patch("cletus_code.run_review.Github")
    def test_workflow_with_kustomize_plugin(
        self,
        mock_github: Mock,
        mock_subprocess: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        mock_kustomize_files: None,
        mock_env: None,
        mock_event_payload: None,
    ):
        """Test workflow with kustomize plugin generating diffs."""
        # Mock kubectl responses
        def mock_kubectl(args, **kwargs):
            result = Mock()
            result.returncode = 0
            if "kustomize" in args:
                result.stdout = "apiVersion: v1\nkind: Service\nmetadata:\n  name: test"
            else:
                result.stdout = ""
            result.stderr = ""
            return result

        mock_subprocess.side_effect = mock_kubectl

        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_pr = Mock()
        mock_pr.number = 42
        mock_pr.title = "Update k8s manifests"
        mock_pr.head.ref = "feature"
        mock_pr.head.sha = "abc123"
        mock_pr.base.ref = "main"
        mock_pr.base.sha = "def456"
        mock_pr.user.login = "developer"
        mock_pr.is_merged.return_value = False
        mock_pr.create_issue_comment.return_value = Mock()

        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_labels.return_value = []
        mock_github.return_value.get_repo.return_value = mock_repo

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=["k8s"],
            workspace_root=workspace,
        )

        # Run plugins
        results = orchestrator._run_plugins(mock_pr)

        # Verify kustomize plugin ran
        assert len(results) == 1
        assert results[0].success is True
        assert "kustomize" in results[0].message.lower() or "rendered" in results[0].message.lower()
        assert results[0].comment_content is not None
        assert "## Kustomize Diff Preview" in results[0].comment_content

    @patch("cletus_code.run_review.subprocess.run")
    @patch("cletus_code.run_review.Github")
    def test_workflow_with_review_rejection(
        self,
        mock_github: Mock,
        mock_subprocess: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
        sample_changed_files: list[str],
        mock_env: None,
        mock_event_payload: None,
    ):
        """Test workflow when review is not approved."""
        mock_subprocess.return_value = Mock(returncode=0)

        mock_repo = Mock()
        mock_repo.full_name = repository
        mock_pr = Mock()
        mock_pr.number = 42
        mock_pr.title = "Add feature"
        mock_pr.head.ref = "feature"
        mock_pr.head.sha = "abc123"
        mock_pr.base.ref = "main"
        mock_pr.base.sha = "def456"
        mock_pr.user.login = "developer"
        mock_pr.is_merged.return_value = False
        mock_pr.create_issue_comment.return_value = Mock()

        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_labels.return_value = []
        mock_github.return_value.get_repo.return_value = mock_repo

        # Create a rejection review
        review_data = {
            "approved": False,
            "overallRisk": "HIGH",
            "summary": "Security vulnerability detected",
            "findings": [
                {
                    "type": "finding",
                    "title": "SQL injection risk",
                    "risk": "HIGH",
                    "summary": "Unsanitized user input in SQL query",
                    "location": {"path": "src/db.py", "line": 42},
                    "tags": ["security", "sql"],
                }
            ],
        }

        output_dir = workspace / "output"
        output_dir.mkdir(exist_ok=True)
        (output_dir / "review.json").write_text(json.dumps(review_data))

        orchestrator = ReviewOrchestrator(
            github_token=github_token,
            changed_files=sample_changed_files,
            workspace_root=workspace,
        )

        with patch.object(orchestrator, "_invoke_claude_code"):
            orchestrator.run()

        # Verify rejection was handled
        review_md = output_dir / "review.md"
        assert review_md.exists()
        markdown = review_md.read_text()
        assert "Needs manual review" in markdown
        assert "HIGH" in markdown
        assert "Security vulnerability" in markdown

        # Verify PR was NOT merged (no approval/merge calls)
        mock_pr.create_review.assert_not_called()
        mock_pr.merge.assert_not_called()

    def test_skill_loading_with_k8s_repo(
        self,
        github_token: str,
        workspace: Path,
    ):
        """Test skill loading for k8s repository."""
        from cletus_code.skills import SkillLoader

        loader = SkillLoader(workspace, "owner/k8s", github_token)

        # Should detect k8s repo
        skill_name = loader._get_repo_skill_name()
        assert skill_name == "k8s-argocd-review"

    def test_skill_loading_with_generic_repo(
        self,
        github_token: str,
        workspace: Path,
    ):
        """Test skill loading for generic repository."""
        from cletus_code.skills import SkillLoader

        loader = SkillLoader(workspace, "owner/my-service", github_token)

        # Should not detect specific skill
        skill_name = loader._get_repo_skill_name()
        assert skill_name is None

        # Should fall back to default
        with patch.object(loader, "_load_from_central_repo", return_value=None):
            skill = loader.load_skill()
            from cletus_code.skills import DEFAULT_GENERAL_SKILL
            assert skill == DEFAULT_GENERAL_SKILL


class TestEndToEndReviewProcessing:
    """Tests for complete review processing pipeline."""

    def test_load_validate_and_build_review(self, workspace: Path, sample_review_data: dict):
        """Test the full pipeline: load, validate, build markdown."""
        import json
        from cletus_code.process_review import validate_review

        # Setup
        review_path = workspace / "review.json"
        review_path.write_text(json.dumps(sample_review_data))

        schema_path = workspace / "schema.json"
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["approved", "overallRisk", "summary"],
            "properties": {
                "approved": {"type": "boolean"},
                "overallRisk": {"type": "string"},
                "summary": {"type": "string"},
                "findings": {"type": "array"},
            },
        }
        schema_path.write_text(json.dumps(schema))

        # Execute
        data = load_review_data(review_path)
        errors = validate_review(data, schema_path)
        markdown = build_markdown(data, errors, None)

        # Verify
        assert data["approved"] is True
        assert len(errors) == 0
        assert "Approved" in markdown
        assert "LOW" in markdown
        assert "LGTM!" in markdown

    def test_review_with_validation_errors(self, workspace: Path):
        """Test review pipeline with validation errors."""
        import json
        from cletus_code.process_review import validate_review

        # Create invalid review - add findings to pass structure validation
        review_data = {
            "approved": True,
            "overallRisk": "INVALID",  # Invalid risk level
            "summary": "Test",
            "findings": [],  # Empty findings so structure validation passes
        }

        review_path = workspace / "review.json"
        review_path.write_text(json.dumps(review_data))

        schema_path = workspace / "schema.json"
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["approved", "overallRisk", "summary"],
            "properties": {
                "approved": {"type": "boolean"},
                "overallRisk": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
                "summary": {"type": "string"},
            },
        }
        schema_path.write_text(json.dumps(schema))

        # Execute
        data = load_review_data(review_path)
        errors = validate_review(data, schema_path)
        markdown = build_markdown(data, errors, None)

        # Verify
        assert len(errors) > 0
        assert "overallRisk" in str(errors)
        assert errors[0] in markdown  # Errors should be in markdown output


class TestPluginIntegration:
    """Integration tests for plugin system."""

    def test_kustomize_plugin_full_workflow(
        self,
        github_token: str,
        repository: str,
        workspace: Path,
        mock_kustomize_files: None,
    ):
        """Test kustomize plugin from detection to output."""
        from cletus_code.plugins import KustomizePlugin, PluginContext

        # Create context
        context = PluginContext(
            pr_number=42,
            repository=repository,
            github_token=github_token,
            workspace_root=workspace,
            pr_dir=workspace / "pull-request",
            base_dir=workspace / "main",
            changed_files=["k8s"],
        )

        plugin = KustomizePlugin()

        # Test detection
        assert plugin.detects(context) is True

        # Test execution (will fail without kubectl, but we can test the path)
        with patch("cletus_code.plugins.kustomize.subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "# Manifest"
            mock_run.return_value = mock_result

            result = plugin.execute(context)

            assert result.success is True
            assert result.comment_content is not None
            assert result.review_context is not None


class TestGitHubUtilsIntegration:
    """Integration tests for GitHub utilities."""

    @patch("cletus_code.github_utils.Github")
    def test_resolve_pr_number_from_event(
        self,
        mock_github: Mock,
        workspace: Path,
        mock_event_payload: None,
        monkeypatch,
    ):
        """Test resolving PR number from event payload."""
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(workspace / "event.json"))

        from cletus_code.github_utils import _resolve_pr_number

        pr_number = _resolve_pr_number()
        assert pr_number == 42

    @patch("cletus_code.github_utils.Github")
    def test_get_pull_request_context(
        self,
        mock_github: Mock,
        github_token: str,
        repository: str,
    ):
        """Test getting pull request context."""
        mock_pr = Mock()
        mock_pr.number = 42
        mock_pr.base.sha = "base123"
        mock_pr.head.sha = "head456"
        mock_pr.merge_commit_sha = None

        mock_repo = Mock()
        mock_repo.get_pull.return_value = mock_pr
        mock_github.return_value.get_repo.return_value = mock_repo

        from cletus_code.github_utils import get_pull_request_context

        context = get_pull_request_context(github_token, repository, 42)

        assert context["pr_number"] == 42
        assert context["base_sha"] == "base123"
        assert context["head_sha"] == "head456"
