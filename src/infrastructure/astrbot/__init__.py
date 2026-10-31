"""AstrBot infrastructure adapters."""

from __future__ import annotations

from .config import (
    clear_config,
    get_config,
    get_plugin_context,
    init_config,
    set_plugin_context,
)

__all__ = [
    "clear_config",
    "get_config",
    "get_plugin_context",
    "init_config",
    "set_plugin_context",
]
