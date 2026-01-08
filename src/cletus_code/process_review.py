"""Validate, render, publish, and optionally merge PR reviews."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def find_file_in_workspace(filename: str, workspace_hint: str = "..") -> Path:
    """Search for a file in the workspace if the provided path doesn't exist."""
    logger.info(f"Searching for file: {filename} in workspace hint: {workspace_hint}")

    # Start with current directory and search upwards
    search_paths = [
        Path.cwd(),  # Current directory
        Path.cwd() / filename,  # Current directory + filename
        Path(workspace_hint),  # Parent directory (workspace root)
        Path(workspace_hint) / filename,  # Parent + filename
        Path("..") / "..",  # Two levels up
        Path("..") / ".." / filename,  # Two levels up + filename
    ]

    # Also search in main/ and pull-request/ directories
    for subdir in ["main", "pull-request"]:
        search_paths.extend([
            Path("..") / subdir,
            Path("..") / subdir / filename,
        ])

    for search_path in search_paths:
        try:
            if search_path.is_file():
                logger.info(f"Found file at: {search_path}")
                return search_path
            elif search_path.is_dir() and (search_path / filename).is_file():
                logger.info(f"Found file at: {search_path / filename}")
                return search_path / filename
        except (OSError, PermissionError) as e:
            logger.debug(f"Cannot access path {search_path}: {e}")
            continue

    # If still not found, try a broader search
    workspace_root = Path("..").resolve()
    try:
        logger.debug(f"Performing broader search from workspace root: {workspace_root}")
        for found_file in workspace_root.rglob(filename):
            try:
                if found_file.is_file():
                    logger.info(f"Found file via broader search at: {found_file}")
                    return found_file
            except (OSError, PermissionError) as e:
                logger.debug(f"Cannot access found file {found_file}: {e}")
                continue
    except (OSError, PermissionError) as e:
        logger.warning(f"Cannot perform broader search from {workspace_root}: {e}")

    # Fallback to original path
    logger.warning(f"File not found, falling back to original path: {filename}")
    return Path(filename)

from github import Github
from github.GithubException import GithubException
from github.PullRequest import PullRequest
from github.Repository import Repository
from jinja2 import Environment, FileSystemLoader, Template
from jsonschema import Draft7Validator

# Local imports - handle both module and script execution
# When run as a script, __package__ is None, so we need to add the parent directory to sys.path
if __package__ is None or __name__ == "__main__":
    # Running as script - add parent directory to path for absolute imports
    import sys
    from pathlib import Path
    # Go up to src directory
    parent_dir = str(Path(__file__).parent.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    # Import from cletus_code package
    from cletus_code.config import (
        get_label_config,
        load_review_config,
        get_auto_merge_config,
    )
    from cletus_code.utils import truncate, normalize_risk, risk_sort_key, make_anchor
else:
    # Running as module - use relative imports
    from .config import (
        get_label_config,
        load_review_config,
        get_auto_merge_config,
    )
    from .utils import truncate, normalize_risk, risk_sort_key, make_anchor


def load_review_data(review_path: Path, validate_structure: bool = True) -> dict[str, Any]:
    """Load and validate review data from JSON file."""
    logger.info(f"Loading review data from: {review_path}")

    if not review_path.exists():
        logger.error(f"Review file not found: {review_path}")
        raise FileNotFoundError(f"expected review JSON at {review_path}")

    if not review_path.is_file():
        logger.error(f"Path is not a file: {review_path}")
        raise ValueError(f"expected {review_path} to be a file")

    # Check file size to avoid empty or extremely large files
    try:
        file_size = review_path.stat().st_size
        if file_size == 0:
            logger.error(f"Review file is empty: {review_path}")
            raise ValueError(f"review file is empty: {review_path}")
        if file_size > 10 * 1024 * 1024:  # 10MB limit
            logger.error(f"Review file too large ({file_size} bytes): {review_path}")
            raise ValueError(f"review file too large ({file_size} bytes): {review_path}")
    except OSError as e:
        logger.error(f"Cannot access review file {review_path}: {e}")
        raise ValueError(f"cannot access review file {review_path}: {e}") from e

    try:
        content = review_path.read_text(encoding='utf-8')
        if not content.strip():
            logger.error(f"Review file contains only whitespace: {review_path}")
            raise ValueError(f"review file is empty or contains only whitespace: {review_path}")

        data = json.loads(content)

        # Basic structure validation
        if not isinstance(data, dict):
            logger.error(f"Review data is not a JSON object: {type(data)}")
            raise ValueError(f"review data must be a JSON object, got {type(data)}")

        if validate_structure:
            required_fields = ["approved", "overallRisk", "summary"]
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                logger.error(f"Review data missing required fields: {missing_fields}")
                raise ValueError(f"review data missing required fields: {missing_fields}")
            if "findings" not in data and "changes" not in data:
                logger.error("Review data missing required field: findings")
                raise ValueError("review data missing required field: findings")

        findings_data = data.get("findings")
        if findings_data is None:
            findings_data = data.get("changes") or []
        version_count = 0
        resource_count = 0
        if isinstance(findings_data, list):
            for item in findings_data:
                if not isinstance(item, dict):
                    continue
                item_type = (item.get("type") or "").lower()
                if item_type == "version" or "component" in item:
                    version_count += 1
                elif item_type == "resource":
                    resource_count += 1
                elif "changeType" in item or "resource" in item:
                    resource_count += 1

        total_changes = len(findings_data) if isinstance(findings_data, list) else 0
        logger.info(
            "Successfully loaded review data with %s version changes and %s resource changes from %s total entries",
            version_count,
            resource_count,
            total_changes,
        )
        return data

    except json.JSONDecodeError as exc:
        logger.error(f"JSON decode error in {review_path}: {exc}")
        raise ValueError(f"unable to parse JSON from {review_path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        logger.error(f"Unicode decode error in {review_path}: {exc}")
        raise ValueError(f"unable to decode file {review_path} as UTF-8: {exc}") from exc
    except OSError as e:
        logger.error(f"File read error for {review_path}: {e}")
        raise ValueError(f"cannot read review file {review_path}: {e}") from e


def validate_review(data: dict[str, Any], schema_path: Path) -> list[str]:
    """Validate review data against JSON schema."""
    logger.info(f"Validating review data against schema: {schema_path}")

    if not schema_path.exists():
        logger.error(f"Schema file not found: {schema_path}")
        raise FileNotFoundError(f"schema file not found: {schema_path}")

    if not schema_path.is_file():
        logger.error(f"Schema path is not a file: {schema_path}")
        raise ValueError(f"expected {schema_path} to be a file")

    try:
        schema_text = schema_path.read_text(encoding='utf-8')
        if not schema_text.strip():
            logger.error(f"Schema file is empty: {schema_path}")
            raise ValueError(f"schema file is empty: {schema_path}")

        schema = json.loads(schema_text)
        logger.debug("Successfully loaded schema")

    except json.JSONDecodeError as exc:
        logger.error(f"Invalid JSON in schema file {schema_path}: {exc}")
        raise ValueError(f"unable to parse schema JSON from {schema_path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        logger.error(f"Unicode decode error in schema file {schema_path}: {exc}")
        raise ValueError(f"unable to decode schema file {schema_path} as UTF-8: {exc}") from exc
    except OSError as e:
        logger.error(f"Cannot read schema file {schema_path}: {e}")
        raise ValueError(f"cannot read schema file {schema_path}: {e}") from e

    try:
        validator = Draft7Validator(schema)
        errors = list(validator.iter_errors(data))
        errors.sort(key=lambda err: list(err.path))

        formatted: list[str] = []
        for error in errors:
            path = "/".join(str(part) for part in error.path) or "<root>"
            formatted.append(f"{path}: {error.message}")

        if formatted:
            logger.warning(f"Schema validation found {len(formatted)} errors")
            for error in formatted[:5]:  # Log first 5 errors
                logger.warning(f"Validation error: {error}")
            if len(formatted) > 5:
                logger.warning(f"... and {len(formatted) - 5} more errors")
        else:
            logger.info("Schema validation passed successfully")

        return formatted

    except Exception as exc:
        logger.error(f"Unexpected error during schema validation: {exc}")
        raise ValueError(f"schema validation failed: {exc}") from exc


def get_template() -> Template:
    """Load Jinja2 template with error handling."""
    template_path = Path(__file__).resolve().parent / "templates"
    logger.debug(f"Loading template from: {template_path}")

    if not template_path.exists():
        logger.error(f"Template directory not found: {template_path}")
        raise FileNotFoundError(f"template directory not found: {template_path}")

    if not template_path.is_dir():
        logger.error(f"Template path is not a directory: {template_path}")
        raise ValueError(f"expected {template_path} to be a directory")

    template_file = template_path / "review.md.j2"
    if not template_file.exists():
        logger.error(f"Template file not found: {template_file}")
        raise FileNotFoundError(f"template file not found: {template_file}")

    if not template_file.is_file():
        logger.error(f"Template path is not a file: {template_file}")
        raise ValueError(f"expected {template_file} to be a file")

    try:
        env = Environment(
            loader=FileSystemLoader(str(template_path)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        template = env.get_template("review.md.j2")
        logger.debug("Template loaded successfully")
        return template
    except Exception as exc:
        logger.error(f"Failed to load template: {exc}")
        raise ValueError(f"failed to load template: {exc}") from exc


def _get_findings(data: dict[str, Any]) -> list[dict[str, Any]]:
    findings_data = data.get("findings")
    if findings_data is None:
        findings_data = data.get("changes")
    if findings_data is None:
        findings_data = []
    if not isinstance(findings_data, list):
        raise ValueError(f"findings must be a list, got {type(findings_data)}")
    return findings_data


def build_markdown(
    data: dict[str, Any],
    validation_errors: list[str],
    automation_note: str | None = None,
    automerged: bool | None = None,
) -> str:
    """Build markdown output from review data with error handling."""
    logger.info("Building markdown output from review data")

    try:
        template = get_template()
    except Exception as exc:
        logger.error(f"Failed to get template: {exc}")
        raise ValueError(f"failed to get template for markdown rendering: {exc}") from exc

    # Validate input data structure
    if not isinstance(data, dict):
        logger.error(f"Invalid data type for build_markdown: {type(data)}")
        raise ValueError(f"expected dict for data, got {type(data)}")

    if not isinstance(validation_errors, list):
        logger.error(f"Invalid validation_errors type: {type(validation_errors)}")
        raise ValueError(f"expected list for validation_errors, got {type(validation_errors)}")

    if automation_note is not None and not isinstance(automation_note, str):
        logger.error(f"Invalid automation_note type: {type(automation_note)}")
        raise ValueError(f"expected str for automation_note, got {type(automation_note)}")

    logger.debug("Processing review findings")

    try:
        findings_data = _get_findings(data)

        normalized_findings = []
        finding_anchor_counter: defaultdict[str, int] = defaultdict(int)

        for i, item in enumerate(findings_data):
            if not isinstance(item, dict):
                logger.warning(f"Skipping invalid finding item at index {i}: {type(item)}")
                continue

            try:
                finding_type = (item.get("type") or "").strip().lower()
                if not finding_type:
                    if "component" in item:
                        finding_type = "version"
                    elif "resource" in item or "changeType" in item:
                        finding_type = "resource"
                    else:
                        finding_type = "finding"

                risk = normalize_risk(item.get("risk"))
                summary = truncate(item.get("summary") or "", 280) or "n/a"

                subject_data = item.get("subject") if isinstance(item.get("subject"), dict) else {}
                component = item.get("component") if isinstance(item.get("component"), dict) else {}
                if not subject_data and component:
                    subject_data = {
                        "kind": component.get("kind"),
                        "name": component.get("name"),
                        "from": component.get("from"),
                        "to": component.get("to"),
                    }

                subject_kind = (subject_data.get("kind") or "").strip()
                subject_name = (subject_data.get("name") or "").strip()
                subject_from = subject_data.get("from")
                subject_to = subject_data.get("to")
                if isinstance(subject_from, str):
                    subject_from = subject_from.strip() or None
                if isinstance(subject_to, str):
                    subject_to = subject_to.strip() or None
                subject = None
                if subject_kind or subject_name:
                    subject = {
                        "kind": subject_kind,
                        "name": subject_name,
                        "from": subject_from,
                        "to": subject_to,
                    }

                location_data = item.get("location") if isinstance(item.get("location"), dict) else {}
                resource = item.get("resource")
                if not location_data and resource:
                    location_data = {"resource": resource}
                location = {}
                location_resource = location_data.get("resource")
                location_path = location_data.get("path")
                location_line = location_data.get("line")
                location_column = location_data.get("column")
                if isinstance(location_resource, str) and location_resource.strip():
                    location["resource"] = location_resource.strip()
                if isinstance(location_path, str) and location_path.strip():
                    location["path"] = location_path.strip()
                if isinstance(location_line, int):
                    location["line"] = location_line
                if isinstance(location_column, int):
                    location["column"] = location_column
                location = location or None

                title = (item.get("title") or "").strip()
                if not title:
                    if subject_name and (subject_from or subject_to):
                        from_label = subject_from or "n/a"
                        to_label = subject_to or "n/a"
                        title = f"{subject_name} {from_label} -> {to_label}"
                    elif subject_name:
                        title = subject_name
                    elif location and location.get("resource"):
                        title = location["resource"]
                    else:
                        title = f"{finding_type} finding"

                tags = []
                tag_set = set()
                tags_data = item.get("tags") or []
                if isinstance(tags_data, list):
                    for tag in tags_data:
                        if not isinstance(tag, str):
                            continue
                        normalized = tag.strip().lower()
                        if not normalized or normalized in tag_set:
                            continue
                        tags.append(normalized)
                        tag_set.add(normalized)

                def add_tag(value: str) -> None:
                    normalized = value.strip().lower()
                    if not normalized or normalized in tag_set:
                        return
                    tags.append(normalized)
                    tag_set.add(normalized)

                change_type = (item.get("changeType") or "").strip().lower()
                if change_type:
                    add_tag(f"change:{change_type}")

                update_kind = ""
                if finding_type == "version":
                    update_kind = (subject_kind or component.get("kind") or "").strip().lower()
                if update_kind:
                    add_tag(f"update:{update_kind}")

                cosmetic = item.get("cosmetic")
                if cosmetic is None:
                    cosmetic = item.get("isCosmetic")
                cosmetic = bool(cosmetic)

                evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
                diff = (evidence.get("diff") or "").strip()
                snippet = (evidence.get("snippet") or "").strip()
                yaml_snippet = (evidence.get("yaml") or "").strip()

                references = []
                references_data = item.get("references") or []
                if isinstance(references_data, list):
                    for ref in references_data:
                        if not isinstance(ref, dict):
                            continue
                        url = (ref.get("url") or "").strip()
                        note = truncate(ref.get("note") or "", 240)
                        if url or note:
                            references.append({"url": url, "note": note})

                anchor = make_anchor(
                    finding_anchor_counter,
                    "finding",
                    title,
                    "finding",
                )

                normalized_findings.append({
                    "type": finding_type,
                    "title": title,
                    "summary": summary,
                    "risk": risk,
                    "tags": tags,
                    "cosmetic": cosmetic,
                    "anchor": anchor,
                    "collapse": risk not in {"HIGH", "MEDIUM"},
                    "subject": subject,
                    "location": location,
                    "diff": diff.splitlines() if diff else [],
                    "snippet": snippet.splitlines() if snippet else [],
                    "yaml": yaml_snippet.splitlines() if yaml_snippet else [],
                    "references": references,
                })

            except Exception as exc:
                logger.warning(f"Error processing finding item at index {i}: {exc}")
                continue

        findings_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for finding in normalized_findings:
            findings_by_type[finding["type"]].append(finding)

        finding_groups = []
        for finding_type in sorted(findings_by_type.keys()):
            entries = findings_by_type[finding_type]
            entries.sort(key=lambda item: (risk_sort_key(item.get("risk")), item.get("title", "")))
            finding_groups.append({"type": finding_type, "findings": entries})

        logger.debug(
            "Processing %s findings across %s groups",
            len(normalized_findings),
            len(finding_groups),
        )

        # Process summary
        summary_text = (data.get("summary") or "").strip()
        if not summary_text:
            logger.warning("Summary is empty, using default")
        headline = summary_text.splitlines()[0].strip() if summary_text else "Automated Review Summary"

        logger.debug(f"Rendering template with headline: {headline}")

        # Render template
        rendered = template.render(
            verdict="Approved" if data.get("approved") else "Needs manual review",
            overall_risk=data.get("overallRisk", "UNKNOWN"),
            summary=summary_text,
            headline=headline,
            finding_groups=finding_groups,
            validation_errors=validation_errors,
            automation_note=automation_note,
            automerged=automerged,
        )

        result = rendered.strip() + "\n"
        logger.info(f"Successfully rendered markdown ({len(result)} chars)")
        return result

    except Exception as exc:
        logger.error(f"Error building markdown: {exc}")
        raise ValueError(f"failed to build markdown output: {exc}") from exc


def _parse_pr_number(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def _should_skip_merge() -> bool:
    override = (os.environ.get("REVIEW_SKIP_MERGE") or "").strip().lower()
    if override in {"1", "true", "yes"}:
        return True
    return os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"


def should_auto_merge(pr: PullRequest, auto_merge_config: dict[str, Any]) -> tuple[bool, str]:
    """Evaluate auto-merge rules for the current PR."""
    if not auto_merge_config.get("enabled", False):
        return False, "disabled in repo config"

    prefixes = auto_merge_config.get("branch_prefixes") or []
    regexes = auto_merge_config.get("branch_regexes") or []
    authors = auto_merge_config.get("author_logins") or []

    if not prefixes and not regexes and not authors:
        return True, "enabled for all PRs"

    branch = ""
    author = ""
    try:
        branch = (pr.head.ref or "").strip()
    except Exception:
        branch = ""
    try:
        author = (pr.user.login or "").strip()
    except Exception:
        author = ""

    matched: list[str] = []

    for prefix in prefixes:
        if isinstance(prefix, str) and branch.startswith(prefix):
            matched.append(f"branch prefix '{prefix}'")

    for pattern in regexes:
        if not isinstance(pattern, str):
            continue
        try:
            if re.search(pattern, branch):
                matched.append(f"branch regex '{pattern}'")
        except re.error as exc:
            logger.warning("Invalid auto-merge branch regex %s: %s", pattern, exc)

    if author and author in authors:
        matched.append(f"author '{author}'")

    if matched:
        return True, "; ".join(matched)

    if branch or author:
        detail = []
        if branch:
            detail.append(f"branch '{branch}'")
        if author:
            detail.append(f"author '{author}'")
        return False, "no rules matched for " + ", ".join(detail)

    return False, "no rules matched"


def load_pull_request(token: str, timeout: int = 30) -> PullRequest:
    """Load pull request information with timeout and error handling."""
    logger.info("Loading pull request information")

    # Validate required environment variables
    repository_name = os.environ.get("GITHUB_REPOSITORY")
    event_path = os.environ.get("GITHUB_EVENT_PATH")

    if not repository_name:
        logger.error("GITHUB_REPOSITORY environment variable is not set")
        raise EnvironmentError("GITHUB_REPOSITORY must be set by the workflow")

    if not event_path:
        logger.error("GITHUB_EVENT_PATH environment variable is not set")
        raise EnvironmentError("GITHUB_EVENT_PATH must be set by the workflow")

    logger.info(f"Repository: {repository_name}, Event path: {event_path}")

    # Load and validate event payload
    try:
        event_path_obj = Path(event_path)
        if not event_path_obj.exists():
            logger.error(f"Event file not found: {event_path}")
            raise FileNotFoundError(f"event file not found: {event_path}")

        if not event_path_obj.is_file():
            logger.error(f"Event path is not a file: {event_path}")
            raise ValueError(f"expected {event_path} to be a file")

        event_text = event_path_obj.read_text(encoding='utf-8')
        if not event_text.strip():
            logger.error("Event file is empty")
            raise ValueError("event file is empty")

        event = json.loads(event_text)
        logger.debug("Successfully loaded event payload")

    except json.JSONDecodeError as exc:
        logger.error(f"Invalid JSON in event file {event_path}: {exc}")
        raise ValueError(f"unable to parse event JSON from {event_path}: {exc}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        logger.error(f"Cannot read event file {event_path}: {exc}")
        raise ValueError(f"cannot read event file {event_path}: {exc}") from exc

    # Extract PR number
    override_value = os.environ.get("REVIEW_PR_NUMBER")
    pr_number = _parse_pr_number(override_value)
    if override_value and pr_number is None:
        logger.error(f"Invalid REVIEW_PR_NUMBER: {override_value}")
        raise ValueError(f"invalid REVIEW_PR_NUMBER: {override_value}")

    if pr_number is None:
        pr_number = _parse_pr_number(event.get("number"))

    if pr_number is None:
        pr_number = _parse_pr_number((event.get("pull_request") or {}).get("number"))

    if pr_number is None:
        inputs = event.get("inputs") or {}
        pr_number = _parse_pr_number(
            inputs.get("pr_number") or inputs.get("pr") or inputs.get("pull_request")
        )

    if pr_number is None:
        logger.error("No pull request number found in event payload")
        raise ValueError("could not determine pull request number from event payload")

    if pr_number <= 0:
        logger.error(f"Invalid pull request number: {pr_number}")
        raise ValueError(f"invalid pull request number: {pr_number}")

    if override_value:
        logger.info(f"Using PR number override: {pr_number}")

    logger.info(f"Pull request number: {pr_number}")

    # Initialize GitHub client with timeout
    try:
        logger.debug("Initializing GitHub client")
        # Note: Using deprecated login_or_token parameter as in original code
        # Consider updating to auth=github.Auth.Token(...) in future
        gh = Github(token, timeout=timeout)
        logger.debug("GitHub client initialized successfully")
    except Exception as exc:
        logger.error(f"Failed to initialize GitHub client: {exc}")
        raise ValueError(f"failed to initialize GitHub client: {exc}") from exc

    # Get repository with retry logic
    max_retries = 3
    for attempt in range(max_retries):
        try:
            logger.debug(f"Getting repository (attempt {attempt + 1}/{max_retries})")
            repo: Repository = gh.get_repo(repository_name)
            logger.debug(f"Successfully retrieved repository: {repository_name}")
            break
        except GithubException as exc:
            logger.warning(f"GitHub API error getting repository (attempt {attempt + 1}): {exc}")
            if attempt == max_retries - 1:
                logger.error(f"Failed to get repository after {max_retries} attempts: {exc}")
                raise ValueError(f"failed to get repository {repository_name}: {exc}") from exc
            time.sleep(2 ** attempt)  # Exponential backoff
        except Exception as exc:
            logger.error(f"Unexpected error getting repository: {exc}")
            raise ValueError(f"unexpected error getting repository {repository_name}: {exc}") from exc

    # Get pull request with retry logic
    for attempt in range(max_retries):
        try:
            logger.debug(f"Getting pull request (attempt {attempt + 1}/{max_retries})")
            pr = repo.get_pull(pr_number)
            logger.info(f"Successfully retrieved pull request #{pr_number}")
            return pr
        except GithubException as exc:
            logger.warning(f"GitHub API error getting pull request (attempt {attempt + 1}): {exc}")
            if attempt == max_retries - 1:
                logger.error(f"Failed to get pull request after {max_retries} attempts: {exc}")
                raise ValueError(f"failed to get pull request #{pr_number}: {exc}") from exc
            time.sleep(2 ** attempt)  # Exponential backoff
        except Exception as exc:
            logger.error(f"Unexpected error getting pull request: {exc}")
            raise ValueError(f"unexpected error getting pull request #{pr_number}: {exc}") from exc


def derive_labels(data: dict[str, Any]) -> dict[str, str]:
    """Derive GitHub labels from review data using configuration.

    Args:
        data: Review data dictionary containing the findings list.

    Returns:
        Dictionary mapping label names to hex color codes.
    """
    labels: dict[str, str] = {}
    config = get_label_config()

    default_color = config.get("default_color", "6f42c1")
    change_type_colors = config.get("change_type_colors", {})
    update_colors = config.get("update_colors", {})
    tag_colors = config.get("tag_colors", {})
    risk_colors = config.get("risk_colors", {})

    prefix_color_maps = {"change": change_type_colors, "update": update_colors}
    if isinstance(tag_colors, dict):
        for prefix, mapping in tag_colors.items():
            if isinstance(mapping, dict) and prefix not in prefix_color_maps:
                prefix_color_maps[prefix] = mapping

    for finding in _get_findings(data):
        if not isinstance(finding, dict):
            continue

        tags = finding.get("tags") or []
        if isinstance(tags, list):
            for tag in tags:
                if not isinstance(tag, str) or ":" not in tag:
                    continue
                prefix, value = tag.strip().lower().split(":", 1)
                if not prefix or not value:
                    continue
                color_map = prefix_color_maps.get(prefix)
                if color_map is None:
                    continue
                labels[f"{prefix}:{value}"] = color_map.get(value, default_color)

        entry_type = (finding.get("type") or "").lower()
        if entry_type == "resource" or "changeType" in finding:
            change_type = (finding.get("changeType") or "other").lower()
            name = f"change:{change_type}"
            labels[name] = change_type_colors.get(change_type, default_color)
        if entry_type == "version":
            subject = finding.get("subject") or {}
            component = finding.get("component") or {}
            update_kind = ""
            if isinstance(subject, dict):
                update_kind = (subject.get("kind") or "").lower()
            if not update_kind and isinstance(component, dict):
                update_kind = (component.get("kind") or "").lower()
            if update_kind:
                name = f"update:{update_kind}"
                labels[name] = update_colors.get(update_kind, default_color)

    overall_risk = (data.get("overallRisk") or "UNKNOWN").upper()
    risk_label = f"risk:{overall_risk.lower()}"
    labels[risk_label] = risk_colors.get(overall_risk, default_color)

    return labels


def apply_labels(pr: PullRequest, labels: dict[str, str]) -> None:
    """Apply labels to pull request with error handling."""
    if not labels:
        logger.info("No labels to apply")
        return

    logger.info(f"Applying {len(labels)} labels to pull request")

    try:
        repo: Repository = pr.base.repo
        logger.debug(f"Repository: {repo.full_name}")
    except Exception as exc:
        logger.error(f"Failed to get repository from PR: {exc}")
        raise ValueError(f"failed to get repository from pull request: {exc}") from exc

    # Get existing labels with error handling
    try:
        existing_labels = repo.get_labels()
        existing = {label.name for label in existing_labels}
        logger.debug(f"Found {len(existing)} existing labels")
    except GithubException as exc:
        logger.warning(f"Failed to get existing labels (continuing anyway): {exc}")
        existing = set()
    except Exception as exc:
        logger.warning(f"Unexpected error getting existing labels (continuing anyway): {exc}")
        existing = set()

    # Create missing labels
    created_count = 0
    config = get_label_config()
    descriptions = config.get("descriptions", {})

    for name, color in labels.items():
        if name not in existing:
            prefix = name.split(":", 1)[0]
            description = descriptions.get(
                prefix, "Automated review metadata label."
            )
            try:
                logger.debug(f"Creating label: {name}")
                repo.create_label(name=name, color=color, description=description)
                created_count += 1
                logger.debug(f"Successfully created label: {name}")
            except GithubException as exc:
                # HTTP 422 indicates the label already exists (possibly with different metadata).
                if exc.status != 422:
                    logger.error(f"Failed to create label {name}: {exc}")
                    raise ValueError(f"failed to create label {name}: {exc}") from exc
                else:
                    logger.debug(f"Label {name} already exists (HTTP 422)")
            except Exception as exc:
                logger.error(f"Unexpected error creating label {name}: {exc}")
                raise ValueError(f"unexpected error creating label {name}: {exc}") from exc
        else:
            logger.debug(f"Label {name} already exists")

    if created_count > 0:
        logger.info(f"Created {created_count} new labels")

    # Apply labels to PR with retry logic
    max_retries = 3
    for attempt in range(max_retries):
        try:
            logger.debug(f"Adding labels to PR (attempt {attempt + 1}/{max_retries})")
            pr.add_to_labels(*labels.keys())
            logger.info(f"Successfully applied {len(labels)} labels to pull request")
            return
        except GithubException as exc:
            logger.warning(f"GitHub API error adding labels (attempt {attempt + 1}): {exc}")
            if attempt == max_retries - 1:
                logger.error(f"Failed to add labels after {max_retries} attempts: {exc}")
                raise ValueError(f"failed to add labels to pull request: {exc}") from exc
            time.sleep(2 ** attempt)  # Exponential backoff
        except Exception as exc:
            logger.error(f"Unexpected error adding labels: {exc}")
            raise ValueError(f"unexpected error adding labels to pull request: {exc}") from exc


def publish_comment(pr: PullRequest, markdown: str) -> None:
    """Publish comment to pull request with error handling and retry logic.

    Only posts a comment if no bot comment already exists on the PR.
    This ensures exactly one comment per review cycle, even if multiple
    workflows run concurrently.
    """
    if not markdown or not markdown.strip():
        logger.warning("Empty markdown content, skipping comment publication")
        return

    logger.info("Publishing review comment to pull request")

    # Validate markdown content
    if len(markdown) > 65536:  # GitHub comment limit
        logger.warning(f"Comment too long ({len(markdown)} chars), truncating to 65536")
        markdown = markdown[:65536] + "\n\n... (truncated due to length)"

    # Check if any bot comment already exists - if so, skip posting
    try:
        comments = pr.get_issue_comments()
        for comment in comments:
            if comment.user.type == "Bot":
                logger.info(f"Bot comment already exists (ID: {comment.id}), skipping post to ensure only one comment per review cycle")
                return
        logger.info("No existing bot comments found, proceeding to post comment")
    except Exception as exc:
        logger.warning(f"Could not check for existing comments: {exc}")
        # Continue to attempt posting

    max_retries = 3
    for attempt in range(max_retries):
        try:
            logger.debug(f"Creating comment (attempt {attempt + 1}/{max_retries})")
            comment = pr.create_issue_comment(markdown)
            if hasattr(comment, 'id'):
                logger.info(f"Successfully created new comment (ID: {comment.id})")
            else:
                logger.info("Successfully published comment")
            return
        except GithubException as exc:
            logger.warning(f"GitHub API error (attempt {attempt + 1}/{max_retries}): {exc}")
            if attempt == max_retries - 1:
                logger.error(f"Failed to publish comment after {max_retries} attempts: {exc}")
                raise ValueError(f"failed to publish comment on pull request: {exc}") from exc
            time.sleep(2 ** attempt)  # Exponential backoff
        except Exception as exc:
            logger.error(f"Unexpected error publishing comment: {exc}")
            raise ValueError(f"unexpected error creating comment on pull request: {exc}") from exc


def approve_and_merge(pr: PullRequest, markdown: str = "Automated approval based on structured review.") -> None:
    """Approve and merge pull request with comprehensive error handling.

    Args:
        pr: PullRequest to approve and merge.
        markdown: Review content to include in the approval body.
    """
    logger.info("Checking if pull request is already merged")

    try:
        if pr.is_merged():
            logger.info("Pull request is already merged, skipping approval and merge")
            return
    except Exception as exc:
        logger.error(f"Failed to check if PR is merged: {exc}")
        raise ValueError(f"failed to check pull request merge status: {exc}") from exc

    logger.info("Approving pull request")

    # Create review (approval) with retry logic
    max_retries = 3
    for attempt in range(max_retries):
        try:
            logger.debug(f"Creating approval review (attempt {attempt + 1}/{max_retries})")
            pr.create_review(
                body=markdown,
                event="APPROVE"
            )
            logger.info("Successfully created approval review")
            break
        except GithubException as exc:
            logger.warning(f"GitHub API error creating review (attempt {attempt + 1}): {exc}")
            if attempt == max_retries - 1:
                logger.error(f"Failed to create review after {max_retries} attempts: {exc}")
                raise ValueError(f"failed to create approval review: {exc}") from exc
            time.sleep(2 ** attempt)  # Exponential backoff
        except Exception as exc:
            logger.error(f"Unexpected error creating review: {exc}")
            raise ValueError(f"unexpected error creating approval review: {exc}") from exc

    logger.info("Merging pull request")

    # Merge PR with retry logic
    merge_result = None
    for attempt in range(max_retries):
        try:
            logger.debug(f"Merging PR (attempt {attempt + 1}/{max_retries})")
            merge_result = pr.merge(merge_method="merge")
            logger.info(f"Successfully merged pull request (SHA: {merge_result.sha if merge_result else 'unknown'})")
            break
        except GithubException as exc:
            logger.warning(f"GitHub API error merging PR (attempt {attempt + 1}): {exc}")
            if attempt == max_retries - 1:
                logger.error(f"Failed to merge PR after {max_retries} attempts: {exc}")
                raise ValueError(f"failed to merge pull request: {exc}") from exc
            time.sleep(2 ** attempt)  # Exponential backoff
        except Exception as exc:
            logger.error(f"Unexpected error merging PR: {exc}")
            raise ValueError(f"unexpected error merging pull request: {exc}") from exc

    # Attempt to delete the branch if the PR originates from the same repository.
    if merge_result:
        try:
            logger.debug("Checking if branch can be deleted")
            head_repo = pr.head.repo
            base_repo = pr.base.repo

            if (
                head_repo is not None
                and base_repo is not None
                and head_repo.full_name == base_repo.full_name
            ):
                ref = pr.head.ref
                logger.info(f"Deleting branch: {ref}")

                # Delete branch with retry logic
                for attempt in range(max_retries):
                    try:
                        logger.debug(f"Deleting branch ref (attempt {attempt + 1}/{max_retries})")
                        base_repo.get_git_ref(f"heads/{ref}").delete()
                        logger.info(f"Successfully deleted branch: {ref}")
                        break
                    except GithubException as exc:
                        logger.warning(f"GitHub API error deleting branch (attempt {attempt + 1}): {exc}")
                        if attempt == max_retries - 1:
                            logger.warning(f"Failed to delete branch after {max_retries} attempts: {exc}")
                            # Don't fail the entire operation for branch deletion failure
                            break
                        time.sleep(2 ** attempt)  # Exponential backoff
                    except Exception as exc:
                        logger.warning(f"Unexpected error deleting branch: {exc}")
                        # Don't fail the entire operation for branch deletion failure
                        break
            else:
                logger.debug("PR originates from different repository, not deleting branch")

        except Exception as exc:
            # Best-effort cleanup - don't fail the entire operation
            logger.warning(f"Failed to delete branch during cleanup (non-critical): {exc}")
    else:
        logger.warning("No merge result available, skipping branch deletion")


def main(argv: Optional[list[str]] = None) -> None:
    """Main function with comprehensive error handling."""
    logger.info("Starting process_review script")

    try:
        # Parse command line arguments
        parser = argparse.ArgumentParser(description="Process and publish PR reviews")
        parser.add_argument("--output-dir", default="output", help="Directory containing review output files")
        parser.add_argument("--schema-file", help="Path to schema file")
        parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
        parser.add_argument("--dry-run", action="store_true", default=os.environ.get("DRY_RUN", "").lower() == "true", help="Validate review and write markdown, but skip PR operations")
        args = parser.parse_args(argv)

        # Configure logging level based on verbose flag
        if args.verbose:
            logger.setLevel(logging.DEBUG)
            logger.info("Verbose logging enabled")

        logger.info(f"Arguments: output_dir={args.output_dir}, schema_file={args.schema_file}, dry_run={args.dry_run}")

        # Validate and setup paths
        review_path = Path(args.output_dir) / "review.json"
        markdown_path = Path(args.output_dir) / "review.md"
        schema_path = Path(args.schema_file) if args.schema_file else Path(".github/workflows/temu-claude-review.schema.json")

        logger.info(f"Initial paths - review: {review_path}, schema: {schema_path}, markdown: {markdown_path}")

        # Use fallback mechanism if files don't exist
        if not review_path.exists():
            logger.info(f"Review file not found at {review_path}, searching workspace")
            found_review = find_file_in_workspace("review.json", "..")
            if found_review.exists():
                logger.info(f"Found review file at: {found_review}")
                review_path = found_review
                # Update output directory to match found review location
                args.output_dir = str(found_review.parent)
                markdown_path = Path(args.output_dir) / "review.md"
                logger.info(f"Updated output directory to: {args.output_dir}")
            else:
                logger.error(f"Review file not found in workspace: {review_path}")
                raise FileNotFoundError(f"review file not found: {review_path}")

        if not schema_path.exists():
            logger.info(f"Schema file not found at {schema_path}, searching workspace")
            found_schema = find_file_in_workspace("temu-claude-review.schema.json", "..")
            if found_schema.exists():
                logger.info(f"Found schema file at: {found_schema}")
                schema_path = found_schema
            else:
                logger.error(f"Schema file not found in workspace: {schema_path}")
                raise FileNotFoundError(f"schema file not found: {schema_path}")

        logger.info(f"Final paths - review: {review_path}, schema: {schema_path}, markdown: {markdown_path}")

        # Load and validate review data
        logger.info("Loading review data")
        data = load_review_data(review_path)

        logger.info("Validating review data against schema")
        validation_errors = validate_review(data, schema_path)

        # Dry run mode - validate and write markdown only, skip PR operations
        if args.dry_run:
            logger.info("Dry run mode: skipping PR operations")

            # Build markdown output
            logger.info("Building markdown output")
            markdown = build_markdown(data, validation_errors, None)

            # Write markdown file
            logger.info(f"Writing markdown to: {markdown_path}")
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text(markdown, encoding='utf-8')
            logger.info(f"Successfully wrote markdown ({len(markdown)} chars)")

            # Report results
            logger.info("=" * 60)
            logger.info("DRY RUN COMPLETE - Review validation results:")
            logger.info(f"  Approved: {data.get('approved', False)}")
            logger.info(f"  Overall Risk: {data.get('overallRisk', 'UNKNOWN')}")
            logger.info(f"  Summary: {data.get('summary', 'No summary')[:80]}")
            logger.info(f"  Findings: {len(data.get('findings', []))} total")
            if validation_errors:
                logger.warning(f"  Validation errors: {len(validation_errors)}")
            else:
                logger.info("  Schema validation: PASSED")
            logger.info(f"  Markdown written to: {markdown_path}")
            logger.info("=" * 60)
            return

        # Validate GitHub token
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            logger.error("GITHUB_TOKEN environment variable is not set")
            raise EnvironmentError("GITHUB_TOKEN must be provided to publish review results")

        if not token.strip():
            logger.error("GITHUB_TOKEN is empty")
            raise EnvironmentError("GITHUB_TOKEN must not be empty")

        logger.info("GitHub token validated successfully")

        # Load pull request information
        logger.info("Loading pull request information")
        try:
            pr = load_pull_request(token)
        except Exception as exc:
            logger.error(f"Failed to load pull request: {exc}")
            raise ValueError(f"failed to load pull request: {exc}") from exc

        # Load repo-level review configuration
        logger.info("Loading review configuration")
        review_config = load_review_config()
        auto_merge_config = get_auto_merge_config(review_config)
        auto_merge_allowed, auto_merge_reason = should_auto_merge(pr, auto_merge_config)
        logger.info(
            "Auto-merge evaluation: allowed=%s, reason=%s",
            auto_merge_allowed,
            auto_merge_reason,
        )

        skip_merge = _should_skip_merge()
        automation_note = None
        automerged = False
        approved = bool(data.get("approved"))

        # Determine automerge status and build markdown
        will_automerge = not skip_merge and not validation_errors and approved and auto_merge_allowed

        # Build markdown output (before PR operations so we can include automerge status)
        logger.info("Building markdown output")
        try:
            markdown = build_markdown(data, validation_errors, automation_note, will_automerge)
            if not markdown or not markdown.strip():
                logger.warning("Generated markdown is empty")
        except Exception as exc:
            logger.error(f"Failed to build markdown: {exc}")
            raise ValueError(f"failed to build markdown output: {exc}") from exc

        # Write markdown file
        logger.info(f"Writing markdown to: {markdown_path}")
        try:
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text(markdown, encoding='utf-8')
            logger.info(f"Successfully wrote markdown ({len(markdown)} chars)")
        except OSError as exc:
            logger.error(f"Failed to write markdown file {markdown_path}: {exc}")
            raise ValueError(f"failed to write markdown file: {exc}") from exc

        # Apply labels
        logger.info("Applying labels to pull request")
        try:
            labels = derive_labels(data)
            apply_labels(pr, labels)
        except Exception as exc:
            logger.error(f"Failed to apply labels: {exc}")
            raise ValueError(f"failed to apply labels: {exc}") from exc

        # Publish comment (single comment with all info including automerge status)
        logger.info("Publishing review comment")
        try:
            publish_comment(pr, markdown)
        except Exception as exc:
            logger.error(f"Failed to publish comment: {exc}")
            raise ValueError(f"failed to publish comment: {exc}") from exc

        # Approve and merge if conditions are met
        if skip_merge:
            logger.info("Skipping approval/merge due to review replay mode")
        elif will_automerge:
            logger.info("Review is approved and validation passed, attempting to approve and merge PR")
            try:
                approve_and_merge(pr, markdown)
                automerged = True
            except Exception as exc:
                logger.error(f"Failed to approve and merge PR: {exc}")
                raise ValueError(f"failed to approve and merge PR: {exc}") from exc
        else:
            if validation_errors:
                logger.warning(f"Skipping approval/merge due to {len(validation_errors)} validation errors")
            if not approved:
                logger.info("Review not approved, skipping approval/merge")
            if approved and not auto_merge_allowed:
                logger.info("Auto-merge disabled, skipping approval/merge")

        logger.info("Process completed successfully")

        # Fail the workflow when schema validation fails so Renovate PRs stay open.
        if validation_errors:
            logger.error(f"Exiting with error code due to {len(validation_errors)} validation errors")
            sys.exit(1)
        else:
            logger.info("All validations passed, exiting successfully")

    except KeyboardInterrupt:
        logger.error("Script interrupted by user")
        sys.exit(130)  # Standard exit code for SIGINT
    except SystemExit:
        # Re-raise SystemExit (includes sys.exit calls)
        raise
    except Exception as exc:
        logger.error(f"Unexpected error in main: {exc}")
        # Print the error for the workflow logs
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
