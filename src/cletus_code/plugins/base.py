"""Base plugin interface for pre-processing steps."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PluginContext:
    """Context provided to plugins during execution."""

    pr_number: int
    repository: str
    github_token: str

    # Paths to checkout directories
    workspace_root: Path
    pr_dir: Path
    base_dir: Path

    # Changed files from the action
    changed_files: list[str] = field(default_factory=list)

    # Event metadata
    event_name: str = "pull_request"
    base_sha: str | None = None
    head_sha: str | None = None

    # Additional plugin data storage
    plugin_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginResult:
    """Result from plugin execution."""

    success: bool
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    # Optional content to be posted as a comment
    comment_content: str | None = None

    # Additional context for Claude review
    review_context: str | None = None


class Plugin(ABC):
    """Base class for review plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name for identification."""

    @abstractmethod
    def detects(self, context: PluginContext) -> bool:
        """Determine if this plugin should run based on the context.

        Args:
            context: The plugin context containing changed files, paths, etc.

        Returns:
            True if this plugin should run for the given context.
        """

    @abstractmethod
    def execute(self, context: PluginContext) -> PluginResult:
        """Execute the plugin logic.

        Args:
            context: The plugin context containing all necessary information.

        Returns:
            PluginResult with success status, message, and optional metadata.
        """

    def _find_kustomization_files(self, context: PluginContext) -> list[Path]:
        """Find kustomization.yaml files in changed directories.

        Args:
            context: The plugin context.

        Returns:
            List of paths to kustomization.yaml files.
        """
        kustomization_files = []

        for changed_path in context.changed_files:
            # Check if any kustomization file exists in the PR checkout
            pr_path = context.pr_dir / changed_path
            if pr_path.exists() and pr_path.is_dir():
                for kustomize_name in ("kustomization.yaml", "kustomization.yml", "Kustomization"):
                    kustomize_path = pr_path / kustomize_name
                    if kustomize_path.exists() and kustomize_path.is_file():
                        kustomization_files.append(kustomize_path)
                        break

        return kustomization_files
