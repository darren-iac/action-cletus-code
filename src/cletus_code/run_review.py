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
        skill_specs: Optional[list[str]] = None,
        extra_skills: Optional[list[str]] = None,
        output_dir: Optional[Path] = None,
    ):
        """Initialize the review orchestrator.

        Args:
            github_token: GitHub token for API access.
            changed_files: List of changed file paths from changed-files action.
            workspace_root: Root directory for workspace operations.
            skill_name: Optional specific skill to use (deprecated, use skill_specs).
            skill_specs: Optional list of skill specifications to load. Empty list uses defaults.
            extra_skills: Optional list of additional skills to add to defaults.
            output_dir: Directory for output files.
        """
        self.github_token = github_token
        self.changed_files = changed_files
        self.workspace_root = workspace_root or Path.cwd()
        self.output_dir = output_dir or self.workspace_root / "output"

        # Support skill_name (backward compat), skill_specs, and extra_skills
        # If skill_specs is provided (non-empty), use only those
        # Otherwise use defaults + extra_skills
        self.skill_specs = skill_specs if skill_specs is not None else ([skill_name] if skill_name else [])
        self.extra_skills = extra_skills or []
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

        # Step 4: Load review skill(s) for analysis
        from .skills import SkillLoader

        skill_loader = SkillLoader(self.workspace_root, self.repository, self.github_token)

        # Build final skill specs list
        # If skill_specs was explicitly provided (non-empty), use only those
        # Otherwise use extra_skills added to defaults
        if self.skill_specs:
            # User explicitly specified skills, use only those (no defaults)
            all_specs = list(self.skill_specs)
            skill = skill_loader.load_skills(all_specs, include_defaults=False)
        else:
            # No explicit skills - use defaults + extras
            all_specs = list(self.extra_skills)
            skill = skill_loader.load_skills(all_specs, include_defaults=True)

        logger.info(f"Loaded review skill(s) ({len(skill)} chars)")

        # Step 5: Build analysis prompt and invoke Claude for review analysis
        # This step does the actual code review work
        analysis_prompt = self._build_analysis_prompt(skill, plugin_results)
        self._invoke_claude_code(analysis_prompt)

        # Step 6: Generate structured JSON output
        # This is a separate step that produces the final review.json
        self._generate_structured_review(pr)

        # Step 7: Validate the structured output before proceeding
        self._validate_structured_output()

        # Step 8: Process and publish review results
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

    def _build_analysis_prompt(self, skill: str, plugin_results: list[PluginResult]) -> str:
        """Build the analysis prompt for code review.

        This prompt is for the initial review/analysis phase where Claude
        examines the code and provides feedback. The structured JSON output
        is generated in a separate step.

        Args:
            skill: Review skill content.
            plugin_results: Results from plugins.

        Returns:
            Complete prompt for Claude Code analysis.
        """
        sections = [skill]

        # Add plugin context
        if plugin_results:
            sections.append("\n## Additional Context\n")

            for result in plugin_results:
                if result.review_context:
                    sections.append(result.review_context)
                    sections.append("")

        # Note: We don't ask for JSON here - that's done in the structured step
        sections.append("""

## Analysis Instructions

Conduct a thorough code review of the changes. Provide your analysis
including:
- Security concerns
- Bug risks
- Performance issues
- Code quality and maintainability
- Testing gaps

Your analysis will be used to generate the final structured review report.
""")

        return "\n".join(sections)

    def _generate_structured_review(self, pr) -> None:
        """Generate the structured review.json using the dedicated skill.

        This is the final step that produces the guaranteed JSON output.

        Args:
            pr: PullRequest object.
        """
        logger.info("Generating structured review JSON")

        # Load the structured output skill
        skill_template = Path(__file__).parent / "templates" / "generate_review_json_skill.md"
        if not skill_template.exists():
            logger.error(f"Structured review skill not found at {skill_template}")
            raise FileNotFoundError(f"Required skill template not found: {skill_template}")

        skill_content = skill_template.read_text()

        # Build context for the structured skill
        # Include information about what was reviewed
        context_parts = [
            f"# PR Context\n",
            f"- **Repository**: {self.repository}\n",
            f"- **PR Number**: {pr.number}\n",
            f"- **PR Title**: {pr.title}\n",
            f"- **Changed Files**: {len(self.changed_files)} files\n",
            f"\n# Files Reviewed\n",
        ]

        for f in self.changed_files:
            context_parts.append(f"- {f}\n")

        context_parts.append("\n# Previous Analysis\n")
        context_parts.append("The review analysis has been completed. Your task is to\n")
        context_parts.append("synthesize this into the final structured JSON report.\n")

        # Combine context with skill
        full_prompt = "\n".join(context_parts) + "\n\n" + skill_content

        # Write prompt for the structured step
        prompt_file = self.output_dir / "structured-review-prompt.md"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(full_prompt)

        # Set environment variable to indicate this is the structured step
        # The action will use this to know where to write the output
        import os
        os.environ["CLETUS_STRUCTURED_OUTPUT_FILE"] = str(self.output_dir / "review.json")

        # Invoke Claude Code for structured output
        self._invoke_claude_code_structured(full_prompt)

    def _invoke_claude_code_structured(self, prompt: str) -> None:
        """Invoke Claude Code for structured JSON output.

        This is a separate invocation specifically for generating the final
        review.json file. It uses the structured output skill that knows
        how to produce pure JSON without markdown fences or extra text.

        Args:
            prompt: The structured output prompt.
        """
        logger.info("Invoking Claude Code for structured output")

        # Write prompt to file
        prompt_file = self.output_dir / "structured-review-prompt.md"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(prompt)

        logger.info(f"Structured output prompt written to {prompt_file}")
        logger.info(f"Output will be written to {self.output_dir / 'review.json'}")

        # In the actual workflow, the Claude Code action would be invoked next
        # with the structured prompt. The action will write directly to review.json

    def _validate_structured_output(self) -> None:
        """Validate the structured review.json before proceeding.

        This is a stop hook that ensures the JSON is well-formed and contains
        all required fields. Fails fast with clear error messages if validation fails.

        Raises:
            FileNotFoundError: If review.json doesn't exist.
            ReviewValidationError: If review.json is invalid.
        """
        logger.info("Validating structured review output")

        from .validate_json import validate_review_json, ReviewValidationError

        review_path = self.output_dir / "review.json"

        try:
            validate_review_json(review_path)
            logger.info("✓ Structured output validation passed")
        except ReviewValidationError as e:
            logger.error(f"✗ Structured output validation failed: {e}")
            if e.missing_fields:
                logger.error(f"  Missing required fields: {', '.join(e.missing_fields)}")
            # Re-raise to fail the workflow
            raise
        except FileNotFoundError:
            logger.error(f"✗ Structured output file not found: {review_path}")
            logger.error("The structured JSON generation step did not produce review.json")
            raise
        except Exception as e:
            logger.error(f"✗ Unexpected validation error: {e}")
            raise

    def _invoke_claude_code(self, prompt: str) -> None:
        """Invoke the Claude Code action.

        This assumes the action is being run from a workflow that will
        call Claude Code. We write the prompt to a file for the action to use.
        We also write the JSON schema file for structured output.

        Args:
            prompt: The prompt to send to Claude Code.
        """
        logger.info("Preparing Claude Code invocation")

        # Write prompt to file
        prompt_file = self.output_dir / "claude-prompt.md"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(prompt)

        logger.info(f"Claude prompt written to {prompt_file}")

        # Copy JSON schema file for structured output
        import shutil
        schema_source = Path(__file__).parent / "templates" / "review-schema.json"
        schema_dest = self.output_dir / "review-schema.json"

        if schema_source.exists():
            shutil.copy(schema_source, schema_dest)
            logger.info(f"Review schema copied to {schema_dest}")
        else:
            logger.warning(f"Review schema not found at {schema_source}")

        # In the actual workflow, the Claude Code action would be invoked next
        # with --json-schema flag pointing to the schema file.
        # The action will use structured output and write to review.json.

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
        CLETUS_SKILLS: JSON array of skill specifications to use
        CLETUS_EXTRA_SKILLS: JSON array of additional skills to add to defaults
        OUTPUT_DIR: Output directory for results
    """
    import argparse

    parser = argparse.ArgumentParser(description="Run Cletus Code review")
    parser.add_argument("--changed-files", help="JSON array of changed file paths")
    parser.add_argument("--skills-json", help="JSON array of skill specifications")
    parser.add_argument("--extra-skills", help="JSON array of additional skills (adds to defaults)")
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

    # Parse skills (JSON array format)
    skill_specs: list[str] = []
    extra_skills: list[str] = []

    # Priority: --skills-json > CLETUS_SKILLS env > --extra-skills > CLETUS_EXTRA_SKILLS env
    skills_input = args.skills_json or os.environ.get("CLETUS_SKILLS", "")
    if skills_input:
        try:
            skill_specs = json.loads(skills_input)
            if not isinstance(skill_specs, list):
                raise ValueError("CLETUS_SKILLS must be a JSON array")
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in CLETUS_SKILLS, treating as comma-separated: {skills_input}")
            skill_specs = [s.strip() for s in skills_input.split(",") if s.strip()]

    # If no skills specified, check for extra skills (adds to defaults)
    if not skill_specs:
        extra_skills_input = args.extra_skills or os.environ.get("CLETUS_EXTRA_SKILLS", "")
        if extra_skills_input:
            try:
                extra_skills = json.loads(extra_skills_input)
                if not isinstance(extra_skills, list):
                    raise ValueError("CLETUS_EXTRA_SKILLS must be a JSON array")
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in CLETUS_EXTRA_SKILLS: {extra_skills_input}")

    # Run orchestrator
    try:
        orchestrator = ReviewOrchestrator(
            github_token=token,
            changed_files=changed_files,
            workspace_root=Path.cwd(),
            skill_specs=skill_specs,
            extra_skills=extra_skills,
            output_dir=Path(args.output_dir),
        )
        orchestrator.run()
    except Exception as e:
        logger.error(f"Review orchestration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
