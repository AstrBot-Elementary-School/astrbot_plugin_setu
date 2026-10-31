"""Configuration singleton manager.

Provides module-level singleton access to the plugin configuration,
following the rsshub plugin pattern.
"""

from __future__ import annotations

from ...application.settings import clear_application_config, set_application_config
from ...shared.config import SetuPluginConfig

_config: SetuPluginConfig | None = None
_plugin_context: object | None = None


def get_config() -> SetuPluginConfig | None:
    """Get the plugin configuration singleton.

    Returns:
        The current SetuPluginConfig instance or None if not initialized.
    """
    return _config


def get_plugin_context() -> object | None:
    """Get the AstrBot plugin context singleton."""
    return _plugin_context


def set_plugin_context(context: object) -> None:
    """Set the AstrBot plugin context singleton."""
    global _plugin_context
    _plugin_context = context


def init_config(config_dict: dict) -> SetuPluginConfig:
    """Initialize config from dict. Called once at plugin init."""
    global _config
    _config = SetuPluginConfig(**config_dict)
    set_application_config(_config)
    return _config


def clear_config() -> None:
    """Clear config singleton (for testing)."""
    global _config, _plugin_context
    _config = None
    _plugin_context = None
    clear_application_config()
