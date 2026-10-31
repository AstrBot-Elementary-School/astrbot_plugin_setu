"""Read-only settings facade for application code.

Infrastructure owns the full AstrBot/Pydantic config object. Application code reads
small settings snapshots so it does not reach into the full runtime config tree.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..shared.config import SetuPluginConfig


@dataclass(frozen=True)
class SetuSettings:
    """Settings needed by Setu use cases."""

    max_count: int
    content_mode: str
    exclude_ai: bool
    max_replenish_rounds: int


_config: SetuPluginConfig | None = None


def set_application_config(config: SetuPluginConfig) -> None:
    """Set the config snapshot used by application settings getters."""
    global _config
    _config = config


def clear_application_config() -> None:
    """Clear application config for tests and plugin shutdown."""
    global _config
    _config = None


def get_setu_settings() -> SetuSettings:
    """Return Setu settings from the current config snapshot."""
    if _config is None:
        return SetuSettings(
            max_count=10,
            content_mode="sfw",
            exclude_ai=True,
            max_replenish_rounds=3,
        )
    return SetuSettings(
        max_count=_config.max_count,
        content_mode=_config.content_mode,
        exclude_ai=_config.exclude_ai,
        max_replenish_rounds=_config.max_replenish_rounds,
    )
