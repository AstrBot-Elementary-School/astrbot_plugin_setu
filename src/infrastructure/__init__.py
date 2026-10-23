"""Infrastructure layer — external concerns and technical details.

Contains implementations for:
- Sending strategies (direct, forward, HTML card)
- Persistence (repositories, file I/O)
- External API clients
- Caching
- Permission checking
"""

from __future__ import annotations

from ..shared import get_logger
from .permission_service import PermissionService
from .persistence import (
    ConfigAccessControlRepo,
    SQLiteFortuneRepo,
    clear_fortune_repo,
    clear_repo,
    get_access_control_repo,
    get_fortune_repo,
    init_access_control_repo,
    init_fortune_repo,
)
from .providers import (
    clear_provider,
    get_provider,
    init_provider,
    init_provider_from_config,
)
from .sending import (
    DirectSendStrategy,
    ForwardSendStrategy,
    HtmlCardFallbackStrategy,
    ImageSender,
    resolve_send_mode,
)

__all__ = [
    "ConfigAccessControlRepo",
    "DirectSendStrategy",
    "ForwardSendStrategy",
    "HtmlCardFallbackStrategy",
    "ImageSender",
    "PermissionService",
    "SQLiteFortuneRepo",
    "clear_fortune_repo",
    "clear_provider",
    "clear_repo",
    "get_access_control_repo",
    "get_fortune_repo",
    "get_logger",
    "get_provider",
    "init_access_control_repo",
    "init_fortune_repo",
    "init_provider",
    "init_provider_from_config",
    "resolve_send_mode",
]
