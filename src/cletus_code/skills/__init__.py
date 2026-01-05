"""Skill loading and management for review guidance.

This module provides the SkillLoader class which supports loading skills from:
- Local .claude/skills/ directories
- Remote GitHub repositories
- Built-in default skills
- Raw URLs
"""

from .loader import SkillLoader, DEFAULT_PR_REVIEW_SKILL, SkillSource

__all__ = ["SkillLoader", "DEFAULT_PR_REVIEW_SKILL", "SkillSource"]
