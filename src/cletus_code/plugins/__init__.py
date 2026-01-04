"""Plugin system for pre-processing steps before review."""

from .base import Plugin, PluginContext, PluginResult
from .kustomize import KustomizePlugin

__all__ = [
    "Plugin",
    "PluginContext",
    "PluginResult",
    "KustomizePlugin",
]
