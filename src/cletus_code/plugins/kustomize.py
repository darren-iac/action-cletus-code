"""Kustomize plugin for generating Kubernetes manifest diffs."""

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from .base import Plugin, PluginContext, PluginResult

logger = logging.getLogger(__name__)


class KustomizePlugin(Plugin):
    """Plugin that detects kustomize directories and generates rendered manifest diffs."""

    @property
    def name(self) -> str:
        return "kustomize"

    def detects(self, context: PluginContext) -> bool:
        """Detect if any kustomization.yaml files are in the changed files."""
        for changed_path in context.changed_files:
            # Check if kustomization file is directly changed or in a changed directory
            pr_path = context.pr_dir / changed_path
            if pr_path.exists():
                if pr_path.is_file() and pr_path.name in (
                    "kustomization.yaml",
                    "kustomization.yml",
                    "Kustomization",
                ):
                    return True
                if pr_path.is_dir():
                    for kustomize_name in (
                        "kustomization.yaml",
                        "kustomization.yml",
                        "Kustomization",
                    ):
                        if (pr_path / kustomize_name).exists():
                            return True
        return False

    def execute(self, context: PluginContext) -> PluginResult:
        """Execute kustomize diff generation.

        Args:
            context: Plugin context with checkout paths and changed files.

        Returns:
            PluginResult with diff content as comment.
        """
        logger.info("Executing kustomize plugin")

        # Find all unique directories containing kustomization files
        renderable_dirs = self._find_renderable_dirs(context)

        if not renderable_dirs:
            return PluginResult(
                success=True,
                message="No renderable kustomize directories found",
                metadata={"renderable_dirs": []},
            )

        logger.info(f"Found {len(renderable_dirs)} renderable directories")

        # Generate rendered manifests for PR and base
        pr_output_file = context.workspace_root / "pr-rendered.yaml"
        base_output_file = context.workspace_root / "base-rendered.yaml"

        try:
            self._render_kustomize(context, renderable_dirs, pr_output_file, context.pr_dir)
            self._render_kustomize(context, renderable_dirs, base_output_file, context.base_dir)
        except subprocess.CalledProcessError as e:
            return PluginResult(
                success=False,
                message=f"Failed to render kustomize: {e}",
                metadata={"error": str(e)},
            )

        # Generate diff
        diff_content = self._generate_diff(base_output_file, pr_output_file)

        # Build markdown comment
        comment = self._build_diff_comment(diff_content, renderable_dirs)

        # Build review context for Claude
        review_context = self._build_review_context(diff_content, renderable_dirs)

        return PluginResult(
            success=True,
            message=f"Generated kustomize diff for {len(renderable_dirs)} directories",
            metadata={"renderable_dirs": renderable_dirs},
            comment_content=comment,
            review_context=review_context,
        )

    def _find_renderable_dirs(self, context: PluginContext) -> list[str]:
        """Find unique directories containing kustomization files.

        Args:
            context: Plugin context.

        Returns:
            List of directory paths relative to repo root.
        """
        seen = set()
        renderable_dirs = []

        for changed_path in context.changed_files:
            pr_path = context.pr_dir / changed_path

            # Find the directory to check
            if pr_path.is_file():
                check_dir = pr_path.parent
            else:
                check_dir = pr_path

            if not check_dir.exists():
                continue

            # Check for kustomization file
            for kustomize_name in ("kustomization.yaml", "kustomization.yml", "Kustomization"):
                kustomize_path = check_dir / kustomize_name
                if kustomize_path.exists() and kustomize_path.is_file():
                    # Get relative path from repo root
                    try:
                        rel_path = str(kustomize_path.relative_to(context.pr_dir).parent)
                        if rel_path not in seen:
                            seen.add(rel_path)
                            renderable_dirs.append(rel_path)
                    except ValueError:
                        # Path is not relative to pr_dir
                        pass
                    break

        return renderable_dirs

    def _render_kustomize(
        self,
        context: PluginContext,
        dirs: list[str],
        output_file: Path,
        checkout_dir: Path,
    ) -> None:
        """Render kustomize directories to a single output file.

        Args:
            context: Plugin context.
            dirs: List of directory paths to render.
            output_file: Path to write rendered output.
            checkout_dir: Base checkout directory (pr_dir or base_dir).

        Raises:
            subprocess.CalledProcessError: If kubectl kustomize fails.
        """
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.unlink(missing_ok=True)

        for dir_path in dirs:
            full_dir = checkout_dir / dir_path
            if not full_dir.exists():
                logger.warning(f"Directory not found: {full_dir}")
                continue

            logger.info(f"Rendering kustomize directory: {full_dir}")

            # Run kubectl kustomize
            result = subprocess.run(
                ["kubectl", "kustomize", str(full_dir), "--enable-helm"],
                capture_output=True,
                text=True,
                check=False,
                env=os.environ.copy(),
            )

            if result.returncode != 0:
                logger.error(f"kubectl kustomize failed for {full_dir}: {result.stderr}")
                raise subprocess.CalledProcessError(result.returncode, result.args, result.stderr)

            # Append to output file with separator
            with open(output_file, "a") as f:
                f.write(f"# --- {dir_path} ---\n")
                f.write(result.stdout)
                f.write("\n")

    def _generate_diff(self, base_file: Path, pr_file: Path) -> str:
        """Generate unified diff between two rendered files.

        Args:
            base_file: Base/branch version output.
            pr_file: PR version output.

        Returns:
            Unified diff string.
        """
        result = subprocess.run(
            ["diff", "-u", str(base_file), str(pr_file)],
            capture_output=True,
            text=True,
            check=False,
        )

        # Diff returns non-zero if files differ, which is expected
        return result.stdout

    def _build_diff_comment(self, diff: str, dirs: list[str]) -> str:
        """Build markdown comment for the diff.

        Args:
            diff: Unified diff output.
            dirs: List of rendered directories.

        Returns:
            Markdown formatted comment.
        """
        lines = ["## Kustomize Diff Preview", ""]

        if not dirs:
            lines.append("No renderable kustomize directories found.")
        else:
            lines.append(f"Rendered {len(dirs)} kustomize directory(ies)")

        lines.append("")
        lines.append("```diff")
        lines.append(diff)
        lines.append("```")

        return "\n".join(lines)

    def _build_review_context(self, diff: str, dirs: list[str]) -> str:
        """Build context for Claude review.

        Args:
            diff: Unified diff output.
            dirs: List of rendered directories.

        Returns:
            Context string for the review prompt.
        """
        lines = [
            "## Kustomize Diff Context",
            "",
            f"The following kustomize directories were rendered and compared:",
        ]

        for dir_path in dirs:
            lines.append(f"  - {dir_path}")

        lines.append("")
        lines.append("### Diff Output")
        lines.append("")
        lines.append("```diff")
        lines.append(diff)
        lines.append("```")

        return "\n".join(lines)
