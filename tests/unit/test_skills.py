"""Unit tests for skills loader."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from cletus_code.skills import SkillLoader, DEFAULT_GENERAL_SKILL


class TestDefaultGeneralSkill:
    """Tests for the default general review skill."""

    def test_default_skill_exists(self):
        """Test that the default skill is defined."""
        assert DEFAULT_GENERAL_SKILL is not None
        assert isinstance(DEFAULT_GENERAL_SKILL, str)
        assert len(DEFAULT_GENERAL_SKILL) > 0

    def test_default_skill_contains_key_sections(self):
        """Test that the default skill contains expected sections."""
        skill = DEFAULT_GENERAL_SKILL

        # Check for key sections - note that the heading uses "5. **Output Format**:" not "## Output Format"
        assert "# General Code Review" in skill
        assert "Output Format" in skill
        assert '"approved"' in skill
        assert '"overallRisk"' in skill
        assert '"findings"' in skill

    def test_default_skill_mentions_json_schema(self):
        """Test that the default skill specifies JSON output format."""
        skill = DEFAULT_GENERAL_SKILL
        assert "JSON" in skill
        assert "approved" in skill
        assert "LOW" in skill or "MEDIUM" in skill or "HIGH" in skill


class TestSkillLoader:
    """Tests for SkillLoader."""

    def test_init(self, github_token: str, repository: str, workspace: Path):
        """Test SkillLoader initialization."""
        loader = SkillLoader(workspace, repository, github_token)

        assert loader.workspace_root == workspace
        assert loader.repository == repository
        assert loader.github_token == github_token

    def test_load_default_skill_when_no_override(
        self,
        github_token: str,
        repository: str,
        workspace: Path,
    ):
        """Test loading default skill when no repo-specific skill exists."""
        loader = SkillLoader(workspace, repository, github_token)

        with patch("cletus_code.github_utils.fetch_file_from_github", return_value=None):
            skill = loader.load_skill()

            # Should fall back to default
            assert skill == DEFAULT_GENERAL_SKILL

    def test_load_explicit_skill(
        self,
        github_token: str,
        repository: str,
        workspace: Path,
    ):
        """Test loading an explicitly named skill."""
        loader = SkillLoader(workspace, repository, github_token)

        custom_skill = "# Custom Review Skill\nCustom content here."

        with patch.object(loader, "_load_from_central_repo", return_value=custom_skill) as mock_load:
            skill = loader.load_skill("python-review")

            # Should load the specified skill
            mock_load.assert_called_once_with("python-review")
            assert skill == custom_skill

    def test_load_falls_back_to_default_on_skill_not_found(
        self,
        github_token: str,
        repository: str,
        workspace: Path,
    ):
        """Test fallback to default when explicit skill is not found."""
        loader = SkillLoader(workspace, repository, github_token)

        with patch.object(loader, "_load_from_central_repo", return_value=None):
            skill = loader.load_skill("nonexistent-skill")

            # Should fall back to default
            assert skill == DEFAULT_GENERAL_SKILL

    def test_get_repo_skill_name_for_k8s(self, github_token: str, workspace: Path):
        """Test repo skill name detection for k8s repo."""
        loader = SkillLoader(workspace, "owner/k8s", github_token)

        skill_name = loader._get_repo_skill_name()
        assert skill_name == "k8s-argocd-review"

    def test_get_repo_skill_name_for_generic_repo(
        self,
        github_token: str,
        workspace: Path,
    ):
        """Test repo skill name for non-k8s repo."""
        loader = SkillLoader(workspace, "owner/python-service", github_token)

        skill_name = loader._get_repo_skill_name()
        assert skill_name is None

    @patch("cletus_code.github_utils.fetch_file_from_github")
    def test_load_from_central_repo_success(
        self,
        mock_fetch: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
    ):
        """Test successful skill loading from central repo."""
        loader = SkillLoader(workspace, repository, github_token)

        expected_content = "# K8s ArgoCD Review\nReview k8s manifests carefully."
        mock_fetch.return_value = expected_content

        content = loader._load_from_central_repo("k8s-argocd-review")

        assert content == expected_content
        mock_fetch.assert_called_once()

        # Check the call arguments - repository name includes the owner
        call_args = mock_fetch.call_args
        assert call_args[1]["repository"] == "test-owner/.github"
        assert call_args[1]["path"] == ".claude/skills/k8s-argocd-review.md"
        assert call_args[1]["token"] == github_token

    @patch("cletus_code.github_utils.fetch_file_from_github")
    def test_load_from_central_repo_not_found(
        self,
        mock_fetch: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
    ):
        """Test skill loading when skill doesn't exist in central repo."""
        loader = SkillLoader(workspace, repository, github_token)
        mock_fetch.return_value = None

        content = loader._load_from_central_repo("nonexistent-skill")

        assert content is None

    @patch("cletus_code.github_utils.fetch_file_from_github")
    def test_load_from_central_repo_error(
        self,
        mock_fetch: Mock,
        github_token: str,
        repository: str,
        workspace: Path,
    ):
        """Test skill loading when an error occurs."""
        loader = SkillLoader(workspace, repository, github_token)
        mock_fetch.side_effect = Exception("GitHub API error")

        content = loader._load_from_central_repo("test-skill")

        assert content is None

    def test_load_k8s_repo_skill_auto_detect(
        self,
        github_token: str,
        workspace: Path,
    ):
        """Test that k8s repo automatically loads k8s-argocd skill."""
        loader = SkillLoader(workspace, "owner/k8s", github_token)

        custom_skill = "# K8s ArgoCD Review\nCustom content."

        with patch.object(loader, "_load_from_central_repo", return_value=custom_skill) as mock_load:
            skill = loader.load_skill()

            # Should have tried to load k8s-argocd-review
            mock_load.assert_called_once_with("k8s-argocd-review")
            assert skill == custom_skill

    def test_load_with_explicit_skill_overrides_auto_detect(
        self,
        github_token: str,
        workspace: Path,
    ):
        """Test that explicit skill parameter overrides auto-detection."""
        loader = SkillLoader(workspace, "owner/k8s", github_token)

        custom_skill = "# Python Review\nPython specific content."

        with patch.object(loader, "_load_from_central_repo", return_value=custom_skill) as mock_load:
            skill = loader.load_skill("python-review")

            # Should load the explicit skill, not auto-detected k8s skill
            mock_load.assert_called_once_with("python-review")
            assert skill == custom_skill
