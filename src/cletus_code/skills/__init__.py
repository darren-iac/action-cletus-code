"""Skill loading and management for review guidance."""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default built-in general review skill
DEFAULT_GENERAL_SKILL = """# General Code Review

You are conducting a code review for a pull request. Your task is to:

1. **Understand the Changes**: Analyze what files were changed and why.

2. **Assess Risk and Impact**: For each significant change, assess:
   - Is this a breaking change?
   - Does it affect security, performance, or reliability?
   - Are there edge cases that weren't considered?

3. **Check for Common Issues**:
   - Logic errors and bugs
   - Security vulnerabilities (injection, XSS, authentication issues, etc.)
   - Performance concerns
   - Error handling and edge cases
   - Code consistency and style
   - Documentation completeness

4. **Provide Constructive Feedback**:
   - Be specific about issues found
   - Suggest concrete improvements
   - Acknowledge good changes
   - Distinguish between critical issues and nitpicks

5. **Output Format**:
   Produce your review as JSON with the following structure:
   ```json
   {
     "approved": true/false,
     "overallRisk": "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN",
     "summary": "Brief summary of the review",
     "findings": [
       {
         "type": "finding",
         "title": "Short descriptive title",
         "risk": "LOW" | "MEDIUM" | "HIGH",
         "summary": "Detailed explanation",
         "location": {
           "path": "path/to/file",
           "line": 42
         },
         "tags": ["security", "performance"],
         "cosmetic": false,
         "evidence": {
           "snippet": "Relevant code snippet",
           "diff": "git diff excerpt"
         },
         "references": [
           {
             "url": "https://example.com",
             "note": "Reference description"
           }
         ]
       }
     ]
   }
   ```

6. **Approval Criteria**:
   - **Approve** if: No critical/high-risk issues found, changes align with intent
   - **Request Changes** if: Any critical issues, breaking changes without discussion, or insufficient context
"""


class SkillLoader:
    """Loads review skills from various sources."""

    def __init__(self, workspace_root: Path, repository: str, github_token: str):
        """Initialize the skill loader.

        Args:
            workspace_root: Root directory of the workspace.
            repository: GitHub repository name (e.g., "owner/repo").
            github_token: GitHub token for API access.
        """
        self.workspace_root = workspace_root
        self.repository = repository
        self.github_token = github_token

    def load_skill(self, skill_name: Optional[str] = None) -> str:
        """Load a review skill, with fallback to default.

        Priority order:
        1. Explicitly named skill from central .github repo
        2. Repo-specific skill from .github/.claude/skills/review.md
        3. Default general skill (built-in)

        Args:
            skill_name: Optional explicit skill name to load.

        Returns:
            The skill content as a string.
        """
        # If skill_name is provided, try to load from central .github repo
        if skill_name:
            skill = self._load_from_central_repo(skill_name)
            if skill:
                logger.info(f"Loaded skill from central repo: {skill_name}")
                return skill
            logger.warning(f"Skill '{skill_name}' not found in central repo, falling back to default")

        # Try to load repo-specific skill from central .github repo
        repo_skill_name = self._get_repo_skill_name()
        if repo_skill_name:
            skill = self._load_from_central_repo(repo_skill_name)
            if skill:
                logger.info(f"Loaded repo-specific skill: {repo_skill_name}")
                return skill

        # Fall back to default general skill
        logger.info("Using default general review skill")
        return DEFAULT_GENERAL_SKILL

    def _get_repo_skill_name(self) -> Optional[str]:
        """Determine the repo-specific skill name.

        Args:
            repository: Repository name (e.g., "owner/repo").

        Returns:
            Skill name for the repo, or None if not applicable.
        """
        # For the k8s repo, use the k8s-argocd skill
        if self.repository.endswith("k8s"):
            return "k8s-argocd-review"

        # Could extend this with more mappings or conventions
        # e.g., repo named "python-service" -> "python-review"
        return None

    def _load_from_central_repo(self, skill_name: str) -> Optional[str]:
        """Load a skill file from the central .github repository.

        Args:
            skill_name: Name of the skill to load (without .md extension).

        Returns:
            Skill content, or None if not found.
        """
        from ..github_utils import fetch_file_from_github

        # Construct the path in the central .github repo
        # Skills are stored at .claude/skills/{skill_name}.md
        owner = self.repository.split("/")[0]
        central_repo = f"{owner}/.github"
        skill_path = f".claude/skills/{skill_name}.md"

        try:
            content = fetch_file_from_github(
                repository=central_repo,
                path=skill_path,
                token=self.github_token,
                ref="main",
            )
            return content
        except Exception as e:
            logger.debug(f"Could not load skill '{skill_name}' from central repo: {e}")
            return None
