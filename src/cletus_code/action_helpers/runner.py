"""
Action runner for Cletus Code Review.

This module handles the GitHub Actions execution, replacing bash scripts
with more reliable Python code.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


def load_json_schema(schema_path: Path) -> Optional[str]:
    """Load and compact JSON schema for inline passing to Claude Code.

    Args:
        schema_path: Path to the JSON schema file

    Returns:
        Compacted JSON string, or None if file doesn't exist
    """
    if not schema_path.exists():
        logger.error("schema_file_not_found", path=str(schema_path))
        return None

    try:
        with open(schema_path, "r") as f:
            schema = json.load(f)
        # Compact to single line for inline passing
        return json.dumps(schema, separators=(",", ":"))
    except Exception as e:
        logger.error("schema_load_failed", path=str(schema_path), error=str(e))
        return None


def write_structured_output(
    structured_output: str,
    output_path: Path,
    max_retries: int = 3,
) -> bool:
    """Write structured output to file with retry logic.

    Args:
        structured_output: JSON string from Claude Code
        output_path: Path to write the output file
        max_retries: Maximum number of retry attempts

    Returns:
        True if write succeeded, False otherwise
    """
    if not structured_output or structured_output == "null":
        logger.warning("structured_output_empty")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, max_retries + 1):
        try:
            # Validate that it's valid JSON
            json.loads(structured_output)

            # Write to file
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(structured_output)

            logger.info(
                "structured_output_written",
                path=str(output_path),
                size=len(structured_output),
                attempt=attempt,
            )
            return True

        except json.JSONDecodeError as e:
            logger.error(
                "invalid_json",
                attempt=attempt,
                max_retries=max_retries,
                error=str(e),
            )
            if attempt >= max_retries:
                return False

        except IOError as e:
            logger.error(
                "write_failed",
                attempt=attempt,
                max_retries=max_retries,
                error=str(e),
            )
            if attempt >= max_retries:
                return False

    return False


def find_schema_file(output_dir: Path, input_schema: Optional[str]) -> Optional[Path]:
    """Find the schema file to use for validation.

    Args:
        output_dir: Directory where review-schema.json might be
        input_schema: Schema file path from input (if provided)

    Returns:
        Path to schema file, or None if not found
    """
    # If input schema is provided, use it
    if input_schema:
        schema_path = Path(input_schema)
        if schema_path.exists():
            return schema_path
        logger.warning("input_schema_not_found", path=str(schema_path))

    # Check for schema in output directory
    schema_path = output_dir / "review-schema.json"
    if schema_path.exists():
        return schema_path

    return None


def get_action_path() -> Path:
    """Get the action path from GitHub Actions environment.

    Returns:
        Path to the action directory
    """
    # GITHUB_ACTION_PATH is set by GitHub Actions
    action_path = os.environ.get("GITHUB_ACTION_PATH", "")
    if action_path:
        return Path(action_path)

    # Fallback to current directory
    return Path.cwd()


def get_workspace_path() -> Path:
    """Get the workspace path from GitHub Actions environment.

    Returns:
        Path to the workspace directory
    """
    # GITHUB_WORKSPACE is set by GitHub Actions
    workspace = os.environ.get("GITHUB_WORKSPACE", "")
    if workspace:
        return Path(workspace)

    # Fallback to current directory
    return Path.cwd()


def run_action(
    changed_files: str,
    skills: Optional[str] = None,
    extra_skills: Optional[str] = None,
    output_dir: str = "output",
    schema_file: Optional[str] = None,
    claude_args: str = "--dangerously-skip-permissions",
) -> int:
    """Run the Cletus Code Review action.

    This is the main entry point for the GitHub Action.

    Args:
        changed_files: JSON array of changed file paths
        skills: JSON array of skills to use
        extra_skills: JSON array of additional skills
        output_dir: Directory for output files
        schema_file: Optional path to schema file
        claude_args: Additional arguments for Claude Code

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    from cletus_code.run_review import main as run_review_main
    from cletus_code.process_review import main as process_review_main

    import argparse

    try:
        # Set up paths
        action_path = get_action_path()
        workspace_path = get_workspace_path()
        output_path = action_path / output_dir

        logger.info(
            "action_start",
            action_path=str(action_path),
            workspace_path=str(workspace_path),
            output_path=str(output_path),
        )

        # Step 1: Run review orchestrator
        logger.info("step_1_run_review_orchestrator")
        os.chdir(action_path)

        review_args = [
            "run_review",
            "--changed-files", changed_files,
            "--output-dir", str(output_path),
        ]

        if skills:
            review_args.extend(["--skills-json", skills])
        if extra_skills:
            review_args.extend(["--extra-skills", extra_skills])

        # Patch sys.argv for the run_review call
        original_argv = sys.argv
        sys.argv = review_args
        try:
            run_review_main()
        finally:
            sys.argv = original_argv

        # Step 2: Load JSON schema for inline passing
        logger.info("step_2_load_json_schema")
        schema_file_path = output_path / "review-schema.json"
        schema_content = load_json_schema(schema_file_path)

        if not schema_content:
            logger.error("schema_load_failed", path=str(schema_file_path))
            return 1

        # Write schema to GITHUB_OUTPUT for next step
        github_output = os.environ.get("GITHUB_OUTPUT")
        if github_output:
            with open(github_output, "a") as f:
                f.write(f"schema={schema_content}\n")
            logger.info("schema_written_to_output")

        # Step 3: Process review results
        logger.info("step_3_process_review")

        # Find schema file for validation
        validation_schema = find_schema_file(output_path, schema_file)

        process_args = [
            "process_review",
            "--output-dir", str(output_path),
        ]

        if validation_schema:
            process_args.extend(["--schema-file", str(validation_schema)])

        # Patch sys.argv for the process_review call
        sys.argv = process_args
        try:
            process_review_main()
        finally:
            sys.argv = original_argv

        logger.info("action_complete")
        return 0

    except Exception as e:
        logger.exception("action_failed", error=str(e))
        return 1


def write_structured_output_from_env(
    output_dir: str = "output",
    fallback_workspace_check: bool = True,
) -> int:
    """Write structured output from environment variable to file.

    This is called from the action step that extracts Claude's structured output.

    Args:
        output_dir: Directory for output files
        fallback_workspace_check: Whether to check workspace as fallback

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    action_path = get_action_path()
    workspace_path = get_workspace_path()
    output_path = action_path / output_dir

    # Get structured output from environment
    structured_output = os.environ.get("STRUCTURED_OUTPUT", "")

    if not structured_output:
        logger.warning("structured_output_env_empty")

        if fallback_workspace_check:
            # Fallback: check workspace
            workspace_review = workspace_path / output_dir / "review.json"
            if workspace_review.exists():
                import shutil
                output_path.mkdir(parents=True, exist_ok=True)
                shutil.copy(workspace_review, output_path / "review.json")
                logger.info("copied_from_workspace", src=str(workspace_review))
                return 0

        logger.error("no_structured_output_found")
        return 1

    # Write with retry logic
    if write_structured_output(structured_output, output_path / "review.json"):
        return 0

    return 1
