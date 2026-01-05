"""GitHub API utilities for file fetching and repository operations."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from github import Github
from github.GithubException import GithubException

logger = logging.getLogger(__name__)


def fetch_file_from_github(
    repository: str,
    path: str,
    token: str,
    ref: str = "main",
) -> Optional[str]:
    """Fetch a file from a GitHub repository.

    Args:
        repository: Repository name (e.g., "owner/repo").
        path: Path to the file in the repository.
        token: GitHub token for authentication.
        ref: Git ref (branch, tag, or commit).

    Returns:
        File content as string, or None if not found.
    """
    try:
        gh = Github(token)
        repo = gh.get_repo(repository)

        contents = repo.get_contents(path, ref=ref)
        if contents is None:
            return None

        if isinstance(contents, list):
            # Path is a directory
            return None

        # Handle both encoded content (for files) and large files
        if hasattr(contents, "decoded_content"):
            return contents.decoded_content.decode("utf-8")
        elif hasattr(contents, "content"):
            import base64

            return base64.b64decode(contents.content).decode("utf-8")
        else:
            return None

    except GithubException as e:
        logger.debug(f"GitHub API error fetching {repository}/{path}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error fetching {repository}/{path}: {e}")
        return None


def get_pull_request_context(
    token: str,
    repository: str,
    pr_number: Optional[int] = None,
) -> dict[str, Any]:
    """Get pull request context including SHAs and metadata.

    Args:
        token: GitHub token.
        repository: Repository name (e.g., "owner/repo").
        pr_number: Pull request number. If None, reads from environment.

    Returns:
        Dictionary with pr_number, base_sha, head_sha, merge_sha.
    """
    # Get PR number from environment if not provided
    if pr_number is None:
        pr_number = _resolve_pr_number()

    gh = Github(token)
    repo = gh.get_repo(repository)
    pr = repo.get_pull(pr_number)

    # Get base SHA
    base_sha = pr.base.sha
    
    # Get head SHA - pr.head.sha should always be available
    head_sha = pr.head.sha
    
    # Fallback: if head_sha is None or empty, try to get from commits
    if not head_sha:
        logger.warning(f"PR #{pr_number} head.sha is None/empty, trying commits API")
        try:
            commits = pr.get_commits()
            if commits.totalCount > 0:
                # Get the last commit (head commit)
                head_sha = commits[commits.totalCount - 1].sha
                logger.info(f"Got head_sha from commits: {head_sha}")
        except Exception as e:
            logger.error(f"Failed to get head_sha from commits: {e}")

    if not head_sha:
        raise ValueError(f"Could not determine head_sha for PR #{pr_number}. base_sha={base_sha}, head.ref={getattr(pr.head, 'ref', 'N/A')}")

    return {
        "pr_number": pr_number,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "merge_sha": pr.merge_commit_sha,
    }


def resolve_rebase_refs(
    token: str,
    repository: str,
    base_sha: str,
    head_sha: str,
    merge_sha: Optional[str],
) -> tuple[str, str]:
    """Resolve the correct base and head SHAs for a rebased branch.

    When a PR is rebased and merged, the original head branch may be deleted.
    This function resolves the correct SHAs by inspecting the merge commit.

    Args:
        token: GitHub token.
        repository: Repository name.
        base_sha: Original base SHA.
        head_sha: Original head SHA.
        merge_sha: Merge commit SHA (if already merged).

    Returns:
        Tuple of (resolved_base_sha, resolved_head_sha).
    """
    if not merge_sha:
        return base_sha, head_sha

    gh = Github(token)
    repo = gh.get_repo(repository)

    try:
        # Get the merge commit to see its parents
        merge_commit = repo.get_commit(merge_sha)
        parents = list(merge_commit.parents)

        if len(parents) >= 2:
            # First parent is base, second is head
            return parents[0].sha, parents[1].sha
        elif len(parents) == 1:
            # Squash merge or single parent
            resolved_base = parents[0].sha

            # Check if head_sha still exists
            try:
                repo.get_commit(head_sha)
                resolved_head = head_sha
            except GithubException:
                # Head commit is gone, use merge commit
                resolved_head = merge_sha

            return resolved_base, resolved_head

    except GithubException as e:
        logger.warning(f"Could not resolve rebase refs: {e}")

    return base_sha, head_sha


def _resolve_pr_number() -> int:
    """Resolve PR number from environment variables.

    Checks:
    1. REVIEW_PR_NUMBER (manual override)
    2. GITHUB_EVENT_PATH (event payload)

    Returns:
        Pull request number.

    Raises:
        ValueError: If PR number cannot be determined.
    """
    # Check for manual override
    override = os.environ.get("REVIEW_PR_NUMBER")
    if override:
        try:
            return int(override)
        except ValueError:
            raise ValueError(f"Invalid REVIEW_PR_NUMBER: {override}")

    # Check event payload
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        raise ValueError("GITHUB_EVENT_PATH not set")

    event_file = Path(event_path)
    if not event_file.exists():
        raise ValueError(f"Event file not found: {event_path}")

    event = json.loads(event_file.read_text())

    # Try various fields where PR number might be
    for key in ["number", "pull_request"]:
        value = event.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, dict):
            number = value.get("number")
            if isinstance(number, int):
                return number

    # Check inputs for workflow_dispatch
    inputs = event.get("inputs") or {}
    for key in ["pr_number", "pr", "pull_request"]:
        value = inputs.get(key)
        if value:
            try:
                return int(value)
            except ValueError:
                pass

    raise ValueError("Could not determine PR number from event payload")
