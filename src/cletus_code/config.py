"""Configuration loader for process_review.

Clean test - triggers self-review.yml to verify single comment behavior.
"""

from copy import deepcopy
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable

import yaml


logger = logging.getLogger(__name__)

DEFAULT_REVIEW_CONFIG: Dict[str, Any] = {
    "auto_merge": {
        "enabled": False,
        "branch_prefixes": [],
        "branch_regexes": [],
        "author_logins": [],
    }
}

DEFAULT_REVIEW_CONFIG_FILES = (
    Path(".github/claude-review.yaml"),
    Path(".github/claude-review.yml"),
    Path(".github/temu-claude-review.yaml"),
    Path(".github/temu-claude-review.yml"),
)

DEFAULT_LABEL_CONFIG_FILES = (
    Path(".github/process_review/config.yaml"),
    Path(".github/process_review/config.yml"),
)


def load_config(config_path: Path = None) -> Dict[str, Any]:
    """Load label and color configuration from YAML file.

    Args:
        config_path: Optional override path to the label config file.

    Returns:
        Dictionary containing configuration with keys:
        - labels.default_color
        - labels.descriptions
        - labels.change_type_colors
        - labels.risk_colors
        - labels.update_colors
    """
    env_override = (os.environ.get("REVIEW_LABEL_CONFIG_PATH") or "").strip()
    if config_path is None and env_override:
        config_path = Path(env_override)

    default_path = Path(__file__).parent / "config.yaml"

    if config_path is None:
        config_path = _search_upwards(DEFAULT_LABEL_CONFIG_FILES)

    if config_path is None:
        config_path = default_path

    if not config_path.exists():
        if config_path != default_path and default_path.exists():
            config_path = default_path
        else:
            logger.warning("Label config not found at %s", config_path)
            return {}

    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - logging only
        logger.warning("Failed to load label config at %s: %s", config_path, exc)
        if config_path != default_path and default_path.exists():
            try:
                return yaml.safe_load(default_path.read_text(encoding="utf-8")) or {}
            except Exception:
                return {}
        return {}

    return data or {}


def get_label_config(config: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get label configuration with defaults.

    Args:
        config: Optional pre-loaded config dict. If not provided, will load from file.

    Returns:
        Dictionary with label configuration including:
        - default_color: str
        - descriptions: dict of prefix -> description
        - change_type_colors: dict of change_type -> hex_color
        - risk_colors: dict of risk_level -> hex_color
        - update_colors: dict of update_type -> hex_color
    """
    if config is None:
        config = load_config()
    return config.get("labels", {})


def _search_upwards(candidates: Iterable[Path]) -> Path | None:
    current = Path.cwd()
    for base in (current, *current.parents):
        for candidate in candidates:
            resolved = base / candidate
            if resolved.is_file():
                return resolved
    return None


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, list):
        items = []
        for entry in value:
            if not isinstance(entry, str):
                continue
            cleaned = entry.strip()
            if cleaned:
                items.append(cleaned)
        return items
    return []


def load_review_config(config_path: Path = None) -> Dict[str, Any]:
    """Load repo-level review configuration from YAML file.

    Args:
        config_path: Optional override path. Defaults to .github/claude-review.yaml
            (or .yml, with a few legacy fallback names).

    Returns:
        Dictionary containing review configuration (auto_merge settings, etc).
        Defaults to safe values when the config is missing or invalid.
    """
    env_override = (os.environ.get("REVIEW_CONFIG_PATH") or "").strip()
    if config_path is None and env_override:
        config_path = Path(env_override)

    if config_path is None:
        config_path = _search_upwards(DEFAULT_REVIEW_CONFIG_FILES)

    if config_path is None or not config_path.exists():
        return deepcopy(DEFAULT_REVIEW_CONFIG)

    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - logging only
        logger.warning("Failed to load review config at %s: %s", config_path, exc)
        return deepcopy(DEFAULT_REVIEW_CONFIG)

    if not isinstance(data, dict):
        logger.warning("Review config %s did not contain a YAML mapping", config_path)
        return deepcopy(DEFAULT_REVIEW_CONFIG)

    merged = deepcopy(DEFAULT_REVIEW_CONFIG)
    merged.update(data)
    return merged


def get_auto_merge_config(config: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get normalized auto-merge configuration with defaults."""
    if config is None:
        config = load_review_config()

    raw = config.get("auto_merge") or {}
    if not isinstance(raw, dict):
        return deepcopy(DEFAULT_REVIEW_CONFIG["auto_merge"])

    allow = raw.get("allow")
    if isinstance(allow, dict):
        criteria = allow
    else:
        criteria = raw

    normalized = {
        "enabled": bool(raw.get("enabled", False)),
        "branch_prefixes": _normalize_string_list(criteria.get("branch_prefixes")),
        "branch_regexes": _normalize_string_list(criteria.get("branch_regexes")),
        "author_logins": _normalize_string_list(criteria.get("author_logins")),
    }
    return normalized
