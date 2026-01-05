"""Main review orchestrator that handles plugins, skills, and Claude invocation."""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from github import Github

from .config import load_review_config, get_auto_merge_config
from .github_utils import (
    get_pull_request_context,
    resolve_rebase_refs,
    _resolve_pr_number,
)
from .plugins import PluginContext, PluginResult, KustomizePlugin
from .process_review import (
    load_review_data,
    validate_review,
    build_markdown,
    apply_labels,
    publish_comment,
    approve_and_merge,
    should_auto_merge,
    _should_skip_merge,
)

logger = logging.getLogger(__name__)


class ReviewOrchestrator:
    """Orchestrates the entire review workflow."""

    def __init__(
        self,
        github_token: str,
        changed_files: list[str],
        workspace_root: Optional[Path] = None,
        skill_name: Optional[str] = None,
        output_dir: Optional[Path] = None,
    ):
        """Initialize the review orchestrator.

        Args:
            github_token: GitHub token for API access.
            changed_files: List of changed file paths from changed-files action.
            workspace_root: Root directory for workspace operations.
            skill_name: Optional specific skill to use.
            output_dir: Directory for output files.
        """
        self.github_token = github_token
        self.changed_files = changed_files
        self.workspace_root = workspace_root or Path.cwd()
        self.output_dir = output_dir or self.workspace_root / "output"
        self.skill_name = skill_name
        self.dry_run = os.environ.get("DRY_RUN", "").lower() == "true"

        # Get repository info from environment
        self.repository = os.environ.get("GITHUB_REPOSITORY", "")
        if not self.repository:
            raise ValueError("GITHUB_REPOSITORY environment variable not set")

        # Initialize GitHub client
        self.gh = Github(github_token)
        self.repo = self.gh.get_repo(self.repository)

        # Setup paths
        self.pr_dir = self.workspace_root / "pull-request"
        self.base_dir = self.workspace_root / "main"

        # Plugins (can be extended)
        self.plugins = [KustomizePlugin()]

    def run(self) -> None:
        """Run the complete review workflow."""
        logger.info("Starting review orchestration")

        # Step 1: Get PR context and setup checkouts
        pr_context = self._setup_pr_context()
        pr = self.repo.get_pull(pr_context["pr_number"])
        logger.info(f"Processing PR #{pr.number}: {pr.title}")

        # Step 2: Checkout PR and base branches
        self._checkout_branches(pr_context)

        # Step 3: Run plugins
        plugin_results = self._run_plugins(pr)
        for result in plugin_results:
            if result.comment_content:
                try:
                    self._post_comment(pr, result.comment_content)
                except Exception as e:
                    logger.warning(f"Failed to post plugin comment: {e}")

        # Step 4: Load review skill
        from .skills import SkillLoader

        skill_loader = SkillLoader(self.workspace_root, self.repository, self.github_token)
        skill = skill_loader.load_skill(self.skill_name)
        logger.info(f"Loaded review skill ({len(skill)} chars)")

        # Step 5: Build Claude prompt with plugin context
        claude_prompt = self._build_claude_prompt(skill, plugin_results)

        # Step 6: Invoke Claude Code action
        self._invoke_claude_code(claude_prompt)

        # Step 7: Process and publish review results
        self._process_review_results(pr)

        logger.info("Review orchestration complete")

    def _setup_pr_context(self) -> dict[str, Any]:
        """Setup pull request context including SHAs.

        Returns:
            Dictionary with pr_number, base_sha, head_sha.
        """
        logger.info("Setting up PR context")

        event_name = os.environ.get("GITHUB_EVENT_NAME", "pull_request")

        # For workflow_dispatch, we need to resolve rebase refs
        if event_name == "workflow_dispatch":
            pr_number = _resolve_pr_number()
            context = get_pull_request_context(self.github_token, self.repository, pr_number)

            # Resolve rebase refs if merge exists
            if context["merge_sha"]:
                logger.info("Resolving rebase refs for workflow_dispatch")
                base_sha, head_sha = resolve_rebase_refs(
                    self.github_token,
                    self.repository,
                    context["base_sha"],
                    context["head_sha"],
                    context["merge_sha"],
                )
            else:
                base_sha, head_sha = context["base_sha"], context["head_sha"]

            return {
                "pr_number": pr_number,
                "base_sha": base_sha,
                "head_sha": head_sha,
                "event_name": event_name,
            }

        # For pull_request event, get from environment
        pr_number = _resolve_pr_number()

        # For PR events, we can get SHAs from the event payload
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if event_path:
            event = json.loads(Path(event_path).read_text())
            pr_data = event.get("pull_request", {})
            return {
                "pr_number": pr_number,
                "base_sha": pr_data.get("base", {}).get("sha"),
                "head_sha": pr_data.get("head", {}).get("sha"),
                "event_name": event_name,
            }

        # Fallback to API
        context = get_pull_request_context(self.github_token, self.repository, pr_number)
        return {
            "pr_number": context["pr_number"],
            "base_sha": context["base_sha"],
            "head_sha": context["head_sha"],
            "event_name": event_name,
        }

    def _checkout_branches(self, pr_context: dict[str, Any]) -> None:
        """Checkout PR and base branches.

        Args:
            pr_context: PR context with SHAs.
        """
        logger.info("Checking out branches")

        # Create directories
        self.pr_dir.mkdir(parents=True, exist_ok=True)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Clone the PR ref
        pr_ref = pr_context["head_sha"]
        base_ref = pr_context["base_sha"]

        logger.info(f"Checking out PR at {pr_ref}")
        subprocess.run(
            ["git", "init"],
            cwd=self.pr_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", f"https://x-access-token:{self.github_token}@github.com/{self.repository}.git"],
            cwd=self.pr_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "fetch", "--depth", "1", "origin", pr_ref],
            cwd=self.pr_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "checkout", pr_ref],
            cwd=self.pr_dir,
            capture_output=True,
            check=True,
        )

        logger.info(f"Checking out base at {base_ref}")
        subprocess.run(
            ["git", "init"],
            cwd=self.base_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", f"https://x-access-token:{self.github_token}@github.com/{self.repository}.git"],
            cwd=self.base_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "fetch", "--depth", "1", "origin", base_ref],
            cwd=self.base_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "checkout", base_ref],
            cwd=self.base_dir,
            capture_output=True,
            check=True,
        )

    def _run_plugins(self, pr) -> list[PluginResult]:
        """Run all applicable plugins.

        Args:
            pr: PullRequest object.

        Returns:
            List of plugin results.
        """
        logger.info("Running plugins")

        results = []
        for plugin in self.plugins:
            try:
                context = PluginContext(
                    pr_number=pr.number,
                    repository=self.repository,
                    github_token=self.github_token,
                    workspace_root=self.workspace_root,
                    pr_dir=self.pr_dir,
                    base_dir=self.base_dir,
                    changed_files=self.changed_files,
                )

                if plugin.detects(context):
                    logger.info(f"Running plugin: {plugin.name}")
                    result = plugin.execute(context)
                    results.append(result)
                    logger.info(f"Plugin {plugin.name}: {result.message}")
                else:
                    logger.debug(f"Plugin {plugin.name} did not detect applicable changes")

            except Exception as e:
                logger.error(f"Plugin {plugin.name} failed: {e}")
                results.append(
                    PluginResult(
                        success=False,
                        message=f"Plugin {plugin.name} failed: {e}",
                    )
                )

        return results

    def _post_comment(self, pr, content: str) -> None:
        """Post a comment to the PR.

        Args:
            pr: PullRequest object.
            content: Markdown content.
        """
        logger.info("Posting plugin comment to PR")
        if self.dry_run:
            logger.info("DRY RUN: Skipping comment posting")
            return
        pr.create_issue_comment(content)

    def _build_claude_prompt(self, skill: str, plugin_results: list[PluginResult]) -> str:
        """Build the Claude Code prompt with skill and plugin context.

        Args:
            skill: Review skill content.
            plugin_results: Results from plugins.

        Returns:
            Complete prompt for Claude Code.
        """
        sections = [skill]

        # Add plugin context
        if plugin_results:
            sections.append("\n## Additional Context\n")

            for result in plugin_results:
                if result.review_context:
                    sections.append(result.review_context)
                    sections.append("")

        return "\n".join(sections)

    def _invoke_claude_code(self, prompt: str) -> None:
        """Invoke the Claude Code action.

        This assumes the action is being run from a workflow that will
        call Claude Code. We write the prompt to a file for the action to use.

        Args:
            prompt: The prompt to send to Claude Code.
        """
        logger.info("Preparing Claude Code invocation")

        # Write prompt to file
        prompt_file = self.output_dir / "claude-prompt.md"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(prompt)

        logger.info(f"Claude prompt written to {prompt_file}")

        # In the actual workflow, the Claude Code action would be invoked next
        # and would read this prompt file. For now, we expect the action to be
        # configured with the prompt as an input.

    def _process_review_results(self, pr) -> None:
        """Process review.json and publish results.

        Args:
            pr: PullRequest object.
        """
        logger.info("Processing review results")

        review_path = self.output_dir / "review.json"

        if not review_path.exists():
            # Check if review.json exists in the PR checkout
            pr_review_path = self.pr_dir / "review.json"
            if pr_review_path.exists():
                review_path = pr_review_path
            else:
                logger.warning("review.json not found, skipping results processing")
                return

        # Load and validate review
        data = load_review_data(review_path)

        # Load schema from workspace or use default
        schema_path = self._find_schema_file()
        validation_errors = []
        if schema_path and schema_path.exists():
            validation_errors = validate_review(data, schema_path)

        # Build markdown
        review_config = load_review_config()
        auto_merge_config = get_auto_merge_config(review_config)
        auto_merge_allowed, auto_merge_reason = should_auto_merge(pr, auto_merge_config)

        skip_merge = _should_skip_merge()
        automation_note = None
        approved = bool(data.get("approved"))

        if skip_merge:
            automation_note = "Auto-merge skipped for this run; verdict above reflects the automated decision."
        elif not auto_merge_allowed:
            if approved and not validation_errors:
                automation_note = f"Auto-merge disabled ({auto_merge_reason}); verdict above reflects what would have been approved."
            else:
                automation_note = f"Auto-merge disabled ({auto_merge_reason})."

        markdown = build_markdown(data, validation_errors, automation_note)

        # Write markdown
        markdown_path = self.output_dir / "review.md"
        markdown_path.write_text(markdown)

        # Apply labels
        labels = self._derive_labels(data)
        apply_labels(pr, labels)

        # Publish comment
        publish_comment(pr, markdown)

        # Approve and merge if conditions met
        if skip_merge:
            logger.info("Skipping approval/merge due to review replay mode")
        elif not validation_errors and approved and auto_merge_allowed:
            logger.info("Review approved, attempting to approve and merge PR")
            approve_and_merge(pr)
        else:
            if validation_errors:
                logger.warning(f"Skipping approval/merge due to {len(validation_errors)} validation errors")
            if not approved:
                logger.info("Review not approved, skipping approval/merge")
            if approved and not auto_merge_allowed:
                logger.info("Auto-merge disabled, skipping approval/merge")

        # Exit with error if validation failed
        if validation_errors:
            logger.error(f"Exiting with error due to {len(validation_errors)} validation errors")
            sys.exit(1)

    def _find_schema_file(self) -> Optional[Path]:
        """Find the schema file for review validation.

        Returns:
            Path to schema file, or None if not found.
        """
        # Check common locations
        candidates = [
            self.workspace_root / ".github" / "workflows" / "temu-claude-review.schema.json",
            self.workspace_root / ".github" / "cletus-review.schema.json",
            self.pr_dir / ".github" / "workflows" / "temu-claude-review.schema.json",
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None

    def _derive_labels(self, data: dict[str, Any]) -> dict[str, str]:
        """Derive labels from review data.

        Args:
            data: Review data dictionary.

        Returns:
            Dictionary mapping label names to hex colors.
        """
        from .process_review import derive_labels
        return derive_labels(data)


def main(argv: Optional[list[str]] = None) -> None:
    """Main entry point for the review orchestrator.

    Environment variables required:
        GITHUB_TOKEN: GitHub token for API access
        GITHUB_REPOSITORY: Repository name (owner/repo)
        GITHUB_EVENT_PATH: Path to event JSON file
        REVIEW_PR_NUMBER: Optional PR number override

    Environment variables optional:
        CHANGED_FILES: JSON array of changed file paths
        CLETUS_SKILL: Skill name to use
        OUTPUT_DIR: Output directory for results
    """
    import argparse

    parser = argparse.ArgumentParser(description="Run Cletus Code review")
    parser.add_argument("--changed-files", help="JSON array of changed file paths")
    parser.add_argument("--skill", help="Specific skill to use")
    parser.add_argument("--output-dir", default="output", help="Output directory")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args(argv)

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Parse changed files
    changed_files: list[str] = []
    if args.changed_files:
        try:
            changed_files = json.loads(args.changed_files)
        except json.JSONDecodeError:
            # If not valid JSON, treat as space/newline separated
            changed_files = [f for f in args.changed_files.split() if f]
    else:
        # Try environment variable
        env_changed = os.environ.get("CHANGED_FILES")
        if env_changed:
            try:
                changed_files = json.loads(env_changed)
            except json.JSONDecodeError:
                changed_files = [f for f in env_changed.split() if f]

    # Get GitHub token
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.error("GITHUB_TOKEN environment variable is required")
        sys.exit(1)

    # Run orchestrator
    try:
        orchestrator = ReviewOrchestrator(
            github_token=token,
            changed_files=changed_files,
            workspace_root=Path.cwd(),
            skill_name=args.skill or os.environ.get("CLETUS_SKILL"),
            output_dir=Path(args.output_dir),
        )
        orchestrator.run()
    except Exception as e:
        logger.error(f"Review orchestration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
