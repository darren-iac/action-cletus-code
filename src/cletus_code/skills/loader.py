"""Enhanced skill loading supporting multiple skills from local and remote sources.

Supported skill sources:
1. Local skills in .claude/skills/{skill-name}/
2. Remote skills from GitHub repos (owner/repo:.claude/skills/{skill-name}/SKILL.md)
3. Default built-in skills (pr-review-toolkit, github-actions-reviewer)
4. Raw URLs to SKILL.md files
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from ..github_utils import fetch_file_from_github

logger = logging.getLogger(__name__)


# Default built-in skills
DEFAULT_PR_REVIEW_SKILL = """# Pull Request Review Toolkit

You are conducting a comprehensive pull request review. Use the following framework:

## Review Focus Areas

### 1. Correctness & Logic
- Does the code accomplish its stated purpose?
- Are there logic errors or edge cases not handled?
- Are there potential race conditions or concurrency issues?
- Is error handling comprehensive?

### 2. Security
- Check for: injection vulnerabilities (SQL, XSS, command, path traversal)
- Authentication/authorization issues
- Sensitive data exposure (secrets, credentials, PII)
- Cryptographic issues (weak algorithms, hardcoded keys)
- Dependency vulnerabilities

### 3. Performance & Scalability
- Inefficient algorithms or data structures
- N+1 queries or missing indexes
- Unnecessary API calls or data fetching
- Memory leaks or resource cleanup issues
- Caching opportunities

### 4. Code Quality & Maintainability
- Code follows project conventions and patterns
- Naming is clear and consistent
- Functions/classes are appropriately sized and focused
- DRY principle is followed (no excessive duplication)
- Comments explain "why", not "what"

### 5. Testing & Documentation
- Changes are adequately tested
- Tests cover edge cases
- Documentation is updated (README, API docs, comments)
- Breaking changes are documented

### 6. API & Interface Design
- Public APIs are well-designed and documented
- Function signatures are intuitive
- Default parameters make sense
- Error types are appropriate

## Output Format

Produce your review as JSON:
```json
{
  "approved": true/false,
  "overallRisk": "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN",
  "summary": "2-3 sentence overview",
  "findings": [
    {
      "type": "finding" | "commendation",
      "title": "Short descriptive title",
      "risk": "LOW" | "MEDIUM" | "HIGH" | "NONE",
      "summary": "Detailed explanation with context",
      "location": {
        "path": "relative/path/to/file",
        "line": 42
      },
      "tags": ["security", "performance", "maintainability"],
      "cosmetic": false,
      "evidence": {
        "snippet": "Relevant code snippet",
        "diff": "git diff excerpt if relevant"
      },
      "references": [
        {
          "url": "https://...",
          "note": "Reference description"
        }
      ]
    }
  ]
}
```

## Approval Criteria

- **Approve** (approved: true): No HIGH/MEDIUM risk findings, or findings are addressed/negligible
- **Request Changes** (approved: false): Any HIGH risk security/correctness finding

## Risk Assessment Guidelines

- **HIGH**: Security vulnerabilities, data loss risk, breaking changes, incorrect core logic
- **MEDIUM**: Performance issues, edge cases, error handling gaps, API design concerns
- **LOW**: Code style, minor optimizations, non-breaking API improvements, documentation
"""


@dataclass
class SkillSource:
    """Represents a skill source."""

    type: str  # 'local', 'github', 'url', 'builtin'
    source: str  # Path, repo:ref, URL, or builtin name
    name: str  # Human-readable name

    def __str__(self) -> str:
        return f"{self.type}:{self.source}"


class SkillLoader:
    """Loads review skills from multiple sources."""

    # Built-in skill registry
    BUILTIN_SKILLS = {
        "pr-review-toolkit": DEFAULT_PR_REVIEW_SKILL,
    }

    # Default skills to always include
    DEFAULT_SKILLS = [
        SkillSource("builtin", "pr-review-toolkit", "PR Review Toolkit"),
    ]

    def __init__(
        self,
        workspace_root: Path,
        repository: str,
        github_token: str,
        default_branch: str = "main",
    ):
        """Initialize the skill loader.

        Args:
            workspace_root: Root directory of the workspace.
            repository: GitHub repository name (e.g., "owner/repo").
            github_token: GitHub token for API access.
            default_branch: Default branch name (default: "main").
        """
        self.workspace_root = workspace_root
        self.repository = repository
        self.github_token = github_token
        self.default_branch = default_branch

    def load_skills(
        self,
        skill_specs: Optional[list[str]] = None,
        include_defaults: bool = True,
    ) -> str:
        """Load multiple skills and combine them.

        Args:
            skill_specs: List of skill specifications. Each can be:
                - "local:skill-name" - Load from .claude/skills/{skill-name}/
                - "owner/repo[:ref]:skill-name" - Load from GitHub repo
                - "url:https://..." - Load from URL
                - "builtin:name" - Load built-in skill
                - "skill-name" - Auto-detect (local, then builtin)
            include_defaults: Whether to include default skills (default: True).

        Returns:
            Combined skill content as a single string.
        """
        if skill_specs is None:
            skill_specs = []

        sources = []

        # Include default skills if requested and no explicit skills provided
        if include_defaults and not skill_specs:
            sources = list(self.DEFAULT_SKILLS)

        # Parse and add user-specified skills
        for spec in skill_specs:
            source = self._parse_skill_spec(spec)
            if source:
                sources.append(source)
                logger.info(f"Added skill source: {source}")
            else:
                logger.warning(f"Could not parse skill spec: {spec}")

        # Load content from all sources
        skill_parts = []
        for source in sources:
            content = self._load_from_source(source)
            if content:
                skill_parts.append(f"## {source.name}\n\n{content}")
            else:
                logger.warning(f"Failed to load skill: {source}")

        if not skill_parts:
            logger.warning("No skills loaded, using default")
            return DEFAULT_PR_REVIEW_SKILL

        return "\n\n---\n\n".join(skill_parts)

    def load_skill(self, skill_name: Optional[str] = None) -> str:
        """Load a single skill (backward compatibility).

        Args:
            skill_name: Optional skill name or spec.

        Returns:
            The skill content as a string.
        """
        if skill_name:
            return self.load_skills([skill_name])
        return self.load_skills([])

    def _parse_skill_spec(self, spec: str) -> Optional[SkillSource]:
        """Parse a skill specification string.

        Supported formats:
        - local:skill-name
        - url:https://example.com/SKILL.md
        - builtin:pr-review-toolkit
        - github:owner/repo[:ref]:skill-path
        - owner/repo[:ref]:skill-path (auto-detected as GitHub)

        Args:
            spec: Skill specification string.

        Returns:
            SkillSource or None if invalid.
        """
        if not spec:
            return None

        # Check for explicit type prefixes first
        if spec.startswith(("local:", "url:", "builtin:", "github:")):
            type_, source = spec.split(":", 1)
            if type_ == "local":
                return SkillSource("local", source, f"Local: {source}")
            elif type_ == "url":
                return SkillSource("url", source, f"URL: {source}")
            elif type_ == "builtin":
                if source in self.BUILTIN_SKILLS:
                    return SkillSource("builtin", source, f"Built-in: {source}")
                logger.warning(f"Unknown built-in skill: {source}")
            elif type_ == "github":
                # github:owner/repo[:ref]:skill-path
                return SkillSource("github", source, f"GitHub: {source}")
            return None

        # Check if it's a URL (before GitHub parsing)
        if self._is_url(spec):
            return SkillSource("url", spec, f"URL: {spec}")

        # GitHub repo format: owner/repo[:ref]:skill-path
        # Must start with owner/repo (one slash, owner has no dots in ref part)
        if "/" in spec:
            parts = spec.split("/")
            if len(parts) >= 2 and "." not in parts[0]:
                # This looks like owner/repo...
                # Now parse the rest which may contain colons
                rest = "/".join(parts[2:]) if len(parts) > 2 else ""
                repo_part = f"{parts[0]}/{parts[1]}"

                # Check if there's a :ref or :path after repo
                if ":" in spec:
                    # Split on first colon after repo
                    repo_part_with_rest = spec.split("/", 2)[2] if len(parts) > 2 else ""
                    colon_parts = spec.split(":")
                    # owner/repo is colon_parts[0] if split on : doesn't affect /
                    # Actually, let's use a different approach
                    pass

                # Simpler: Use split(":") on the whole spec
                colon_parts = spec.split(":")
                if len(colon_parts) >= 2:
                    # First part is owner/repo
                    repo_part = colon_parts[0]
                    # Check if second part looks like a ref (no slashes, short)
                    if len(colon_parts) >= 3 and "/" not in colon_parts[1]:
                        ref = colon_parts[1]
                        skill_path = ":".join(colon_parts[2:])
                    else:
                        # Second part is part of the path
                        ref = self.default_branch
                        skill_path = ":".join(colon_parts[1:])
                    return SkillSource(
                        "github",
                        f"{repo_part}:{ref}:{skill_path}",
                        f"{repo_part}:{skill_path}",
                    )

        # Check if it's a local skill
        local_path = self.workspace_root / ".claude" / "skills" / spec / "SKILL.md"
        if local_path.exists():
            return SkillSource("local", spec, f"Local: {spec}")

        # Check if it's a built-in skill
        if spec in self.BUILTIN_SKILLS:
            return SkillSource("builtin", spec, f"Built-in: {spec}")

        # Treat as local skill (will fail if not found)
        return SkillSource("local", spec, f"Local: {spec}")

    def _is_url(self, s: str) -> bool:
        """Check if string is a URL."""
        try:
            result = urlparse(s)
            return result.scheme in ("http", "https") and result.netloc
        except Exception:
            return False

    def _load_from_source(self, source: SkillSource) -> Optional[str]:
        """Load skill content from a source.

        Args:
            source: SkillSource to load from.

        Returns:
            Skill content or None if not found.
        """
        if source.type == "local":
            return self._load_local(source.source)
        elif source.type == "github":
            return self._load_github(source.source)
        elif source.type == "url":
            return self._load_url(source.source)
        elif source.type == "builtin":
            return self.BUILTIN_SKILLS.get(source.source)
        return None

    def _load_local(self, skill_name: str) -> Optional[str]:
        """Load a local skill from .claude/skills/{skill-name}/SKILL.md.

        Args:
            skill_name: Name of the skill directory.

        Returns:
            Skill content or None if not found.
        """
        skill_path = self.workspace_root / ".claude" / "skills" / skill_name / "SKILL.md"

        if not skill_path.exists():
            logger.debug(f"Local skill not found: {skill_path}")
            return None

        try:
            return skill_path.read_text()
        except Exception as e:
            logger.warning(f"Failed to read local skill {skill_name}: {e}")
            return None

    def _load_github(self, spec: str) -> Optional[str]:
        """Load a skill from a GitHub repository.

        Args:
            spec: Format "owner/repo:ref:skill-path"

        Returns:
            Skill content or None if not found.
        """
        parts = spec.split(":")
        if len(parts) < 3:
            logger.warning(f"Invalid GitHub skill spec: {spec}")
            return None

        repo = parts[0]
        ref = parts[1]
        # Remaining parts form the path (in case path contains :)
        skill_path = ":".join(parts[2:])

        # Ensure path has SKILL.md
        if not skill_path.endswith("SKILL.md"):
            skill_path = f"{skill_path}/SKILL.md"

        try:
            content = fetch_file_from_github(
                repository=repo,
                path=skill_path,
                token=self.github_token,
                ref=ref,
            )
            return content
        except Exception as e:
            logger.warning(f"Failed to load skill from GitHub {spec}: {e}")
            return None

    def _load_url(self, url: str) -> Optional[str]:
        """Load a skill from a URL.

        Args:
            url: URL to the SKILL.md file.

        Returns:
            Skill content or None if not found.
        """
        try:
            import urllib.request

            logger.info(f"Fetching skill from URL: {url}")
            with urllib.request.urlopen(url, timeout=10) as response:
                return response.read().decode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to load skill from URL {url}: {e}")
            return None

    def _get_repo_skill_name(self) -> Optional[str]:
        """Determine the repo-specific skill name.

        Returns:
            Skill name for the repo, or None if not applicable.
        """
        # Check for .cletus-skills config file
        config_path = self.workspace_root / ".cletus-skills"
        if config_path.exists():
            try:
                content = config_path.read_text().strip()
                if content:
                    logger.info(f"Found .cletus-skills config: {content}")
                    return content
            except Exception as e:
                logger.warning(f"Failed to read .cletus-skills: {e}")

        # Auto-detect based on repo name or conventions
        if self.repository.endswith("k8s"):
            return "k8s-argocd-review"

        return None
