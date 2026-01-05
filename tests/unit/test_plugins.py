"""Unit tests for plugins."""

from pathlib import Path
from unittest.mock import Mock, patch


from cletus_code.plugins.base import PluginContext, PluginResult
from cletus_code.plugins.kustomize import KustomizePlugin


class TestPluginContext:
    """Tests for PluginContext."""

    def test_create_context(self, github_token: str, repository: str, workspace: Path, sample_changed_files: list[str]):
        """Test creating a plugin context."""
        context = PluginContext(
            pr_number=42,
            repository=repository,
            github_token=github_token,
            workspace_root=workspace,
            pr_dir=workspace / "pull-request",
            base_dir=workspace / "main",
            changed_files=sample_changed_files,
        )

        assert context.pr_number == 42
        assert context.repository == repository
        assert context.github_token == github_token
        assert context.workspace_root == workspace
        assert context.pr_dir == workspace / "pull-request"
        assert context.base_dir == workspace / "main"
        assert context.changed_files == sample_changed_files
        assert context.event_name == "pull_request"
        assert context.base_sha is None
        assert context.head_sha is None
        assert context.plugin_data == {}


class TestPluginResult:
    """Tests for PluginResult."""

    def test_create_result_success(self):
        """Test creating a successful plugin result."""
        result = PluginResult(
            success=True,
            message="Plugin executed successfully",
            metadata={"dirs_processed": 3},
            comment_content="# Comment",
            review_context="## Context",
        )

        assert result.success is True
        assert result.message == "Plugin executed successfully"
        assert result.metadata == {"dirs_processed": 3}
        assert result.comment_content == "# Comment"
        assert result.review_context == "## Context"

    def test_create_result_failure(self):
        """Test creating a failed plugin result."""
        result = PluginResult(
            success=False,
            message="Plugin failed",
        )

        assert result.success is False
        assert result.message == "Plugin failed"
        assert result.metadata == {}
        assert result.comment_content is None
        assert result.review_context is None


class TestKustomizePlugin:
    """Tests for KustomizePlugin."""

    def test_plugin_name(self):
        """Test plugin name property."""
        plugin = KustomizePlugin()
        assert plugin.name == "kustomize"

    def test_detects_kustomize_file_directly_changed(
        self,
        github_token: str,
        repository: str,
        workspace: Path,
        sample_changed_files: list[str],
    ):
        """Test detection when kustomization.yaml is directly changed."""
        # Create the kustomization file
        kustomize_dir = workspace / "pull-request" / "k8s"
        kustomize_dir.mkdir(parents=True)
        (kustomize_dir / "kustomization.yaml").write_text("apiVersion: kustomize.config.k8s.io/v1beta1")

        context = PluginContext(
            pr_number=42,
            repository=repository,
            github_token=github_token,
            workspace_root=workspace,
            pr_dir=workspace / "pull-request",
            base_dir=workspace / "main",
            changed_files=["k8s/kustomization.yaml"],
        )

        plugin = KustomizePlugin()
        assert plugin.detects(context) is True

    def test_detects_kustomize_file_in_changed_directory(
        self,
        github_token: str,
        repository: str,
        workspace: Path,
    ):
        """Test detection when kustomization.yaml exists in a changed directory."""
        # Create the kustomization file
        kustomize_dir = workspace / "pull-request" / "k8s"
        kustomize_dir.mkdir(parents=True)
        (kustomize_dir / "kustomization.yaml").write_text("apiVersion: kustomize.config.k8s.io/v1beta1")

        context = PluginContext(
            pr_number=42,
            repository=repository,
            github_token=github_token,
            workspace_root=workspace,
            pr_dir=workspace / "pull-request",
            base_dir=workspace / "main",
            changed_files=["k8s"],  # Directory changed
        )

        plugin = KustomizePlugin()
        assert plugin.detects(context) is True

    def test_detects_no_kustomize(
        self,
        github_token: str,
        repository: str,
        workspace: Path,
    ):
        """Test detection when no kustomization files exist."""
        # Create a non-kustomize file
        python_dir = workspace / "pull-request" / "src"
        python_dir.mkdir(parents=True)
        (python_dir / "main.py").write_text("print('hello')")

        context = PluginContext(
            pr_number=42,
            repository=repository,
            github_token=github_token,
            workspace_root=workspace,
            pr_dir=workspace / "pull-request",
            base_dir=workspace / "main",
            changed_files=["src/main.py"],
        )

        plugin = KustomizePlugin()
        assert plugin.detects(context) is False

    def test_detects_kustomize_yml_extension(
        self,
        github_token: str,
        repository: str,
        workspace: Path,
    ):
        """Test detection with .yml extension."""
        kustomize_dir = workspace / "pull-request" / "k8s"
        kustomize_dir.mkdir(parents=True)
        (kustomize_dir / "kustomization.yml").write_text("apiVersion: kustomize.config.k8s.io/v1beta1")

        context = PluginContext(
            pr_number=42,
            repository=repository,
            github_token=github_token,
            workspace_root=workspace,
            pr_dir=workspace / "pull-request",
            base_dir=workspace / "main",
            changed_files=["k8s/kustomization.yml"],
        )

        plugin = KustomizePlugin()
        assert plugin.detects(context) is True

    def test_detects_kustomization_capitalized(
        self,
        github_token: str,
        repository: str,
        workspace: Path,
    ):
        """Test detection with capitalized Kustomization filename."""
        kustomize_dir = workspace / "pull-request" / "k8s"
        kustomize_dir.mkdir(parents=True)
        (kustomize_dir / "Kustomization").write_text("apiVersion: kustomize.config.k8s.io/v1beta1")

        context = PluginContext(
            pr_number=42,
            repository=repository,
            github_token=github_token,
            workspace_root=workspace,
            pr_dir=workspace / "pull-request",
            base_dir=workspace / "main",
            changed_files=["k8s/Kustomization"],
        )

        plugin = KustomizePlugin()
        assert plugin.detects(context) is True

    @patch("cletus_code.plugins.kustomize.subprocess.run")
    def test_execute_success(self, mock_subprocess_run: Mock, github_token: str, repository: str, workspace: Path):
        """Test successful execution of kustomize plugin."""
        # Setup kustomize files
        kustomize_dir = workspace / "pull-request" / "k8s"
        kustomize_dir.mkdir(parents=True)
        (kustomize_dir / "kustomization.yaml").write_text("apiVersion: kustomize.config.k8s.io/v1beta1")

        base_kustomize_dir = workspace / "main" / "k8s"
        base_kustomize_dir.mkdir(parents=True)
        (base_kustomize_dir / "kustomization.yaml").write_text("apiVersion: kustomize.config.k8s.io/v1beta1")

        # Mock subprocess responses
        def mock_run_side_effect(args, **kwargs):
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "# Generated manifest\napiVersion: v1\nkind: Service"
            mock_result.stderr = ""
            return mock_result

        mock_subprocess_run.side_effect = mock_run_side_effect

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
        result = plugin.execute(context)

        assert result.success is True
        assert "kustomize" in result.message.lower()
        assert result.comment_content is not None
        assert result.review_context is not None
        assert "## Kustomize Diff Preview" in result.comment_content

    @patch("cletus_code.plugins.kustomize.subprocess.run")
    def test_execute_no_renderable_dirs(
        self,
        mock_subprocess_run: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
    ):
        """Test execution when no renderable directories are found."""
        context = PluginContext(
            pr_number=42,
            repository=repository,
            github_token=github_token,
            workspace_root=workspace,
            pr_dir=workspace / "pull-request",
            base_dir=workspace / "main",
            changed_files=["src/main.py"],  # No kustomize files
        )

        plugin = KustomizePlugin()
        result = plugin.execute(context)

        assert result.success is True
        assert "no renderable" in result.message.lower()
        assert result.metadata["renderable_dirs"] == []
        assert result.comment_content is None

    @patch("cletus_code.plugins.kustomize.subprocess.run")
    def test_execute_kubectl_fails(self, mock_subprocess_run: Mock, github_token: str, repository: str, workspace: Path):
        """Test execution when kubectl kustomize fails."""
        # Setup kustomize file
        kustomize_dir = workspace / "pull-request" / "k8s"
        kustomize_dir.mkdir(parents=True)
        (kustomize_dir / "kustomization.yaml").write_text("apiVersion: kustomize.config.k8s.io/v1beta1")

        # Mock kubectl failure
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Error: invalid kustomization"
        mock_subprocess_run.return_value = mock_result

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
        result = plugin.execute(context)

        assert result.success is False
        assert "failed to render" in result.message.lower()

    def test_find_renderable_dirs(self, github_token: str, repository: str, workspace: Path):
        """Test finding renderable directories."""
        # Create multiple kustomize directories
        for dir_name in ["k8s/app1", "k8s/app2"]:
            kustomize_dir = workspace / "pull-request" / dir_name
            kustomize_dir.mkdir(parents=True)
            (kustomize_dir / "kustomization.yaml").write_text("apiVersion: kustomize.config.k8s.io/v1beta1")

        context = PluginContext(
            pr_number=42,
            repository=repository,
            github_token=github_token,
            workspace_root=workspace,
            pr_dir=workspace / "pull-request",
            base_dir=workspace / "main",
            changed_files=["k8s/app1", "k8s/app2"],
        )

        plugin = KustomizePlugin()
        dirs = plugin._find_renderable_dirs(context)

        assert len(dirs) == 2
        assert "k8s/app1" in dirs
        assert "k8s/app2" in dirs

    def test_find_renderable_dirs_deduplicates(
        self,
        github_token: str,
        repository: str,
        workspace: Path,
    ):
        """Test that duplicate directories are deduplicated."""
        kustomize_dir = workspace / "pull-request" / "k8s"
        kustomize_dir.mkdir(parents=True)
        (kustomize_dir / "kustomization.yaml").write_text("apiVersion: kustomize.config.k8s.io/v1beta1")

        context = PluginContext(
            pr_number=42,
            repository=repository,
            github_token=github_token,
            workspace_root=workspace,
            pr_dir=workspace / "pull-request",
            base_dir=workspace / "main",
            changed_files=["k8s", "k8s/deployment.yaml", "k8s/service.yaml"],  # k8s appears multiple times
        )

        plugin = KustomizePlugin()
        dirs = plugin._find_renderable_dirs(context)

        assert len(dirs) == 1
        assert dirs[0] == "k8s"
