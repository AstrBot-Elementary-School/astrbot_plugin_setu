"""Persistence layer — data access and storage.

Contains repository implementations for:
- Access control (blacklist/whitelist)
- Fortune data
- Cache management
"""

from __future__ import annotations

from pathlib import Path

from ...shared.config.models import SafetyConfig
from .access_control_repo import ConfigAccessControlRepo
from .sqlite_fortune_repository import SQLiteFortuneRepo

__all__ = [
    "ConfigAccessControlRepo",
    "SQLiteFortuneRepo",
    "clear_fortune_repo",
    "clear_repo",
    "get_access_control_repo",
    "get_fortune_repo",
    "init_access_control_repo",
    "init_fortune_repo",
]

# ==================== Singleton Pattern ====================

_repo: ConfigAccessControlRepo | None = None
_fortune_repo: SQLiteFortuneRepo | None = None


def get_access_control_repo() -> ConfigAccessControlRepo:
    """Get the access control repository singleton.

    Returns:
        The current ConfigAccessControlRepo instance.

    Raises:
        RuntimeError: If repo not initialized.
    """
    if _repo is None:
        raise RuntimeError(
            "Access control repo not initialized. Call init_access_control_repo() first."
        )
    return _repo


async def init_access_control_repo(safety: SafetyConfig) -> ConfigAccessControlRepo:
    """Initialize the read-only access-control snapshot."""
    global _repo
    _repo = ConfigAccessControlRepo(safety)
    return _repo


def clear_repo() -> None:
    """Clear repo singleton (for testing)."""
    global _repo
    _repo = None


def get_fortune_repo() -> SQLiteFortuneRepo:
    """Get the fortune repository singleton."""
    if _fortune_repo is None:
        raise RuntimeError(
            "Fortune repo not initialized. Call init_fortune_repo() first."
        )
    return _fortune_repo


async def init_fortune_repo(data_dir: Path) -> SQLiteFortuneRepo:
    global _fortune_repo
    _fortune_repo = SQLiteFortuneRepo()
    return _fortune_repo


def clear_fortune_repo() -> None:
    """Clear fortune repo singleton."""
    global _fortune_repo
    _fortune_repo = None
