"""Domain layer for AstrBot Setu plugin.

Contains value objects, exceptions, enums, and domain services following
Domain-Driven Design principles.
"""

from __future__ import annotations

from .access_control import AccessPolicy
from .constants import COMMAND_PATTERN, FORTUNE_PATTERN, HTTP_TIMEOUT_SECONDS
from .enums import (
    AccessControlMode,
    ApiType,
    ContentMode,
    MultiApiStrategy,
    SendMode,
)
from .exceptions import (
    AccessDeniedError,
    FortuneException,
    FortuneNotFoundError,
    ProviderError,
    SendError,
    SetuException,
    ValidationError,
)
from .fortune import (
    FortuneGenerationRequest,
    FortuneRecord,
)
from .setu import SetuRequest, TagResolverService

__all__ = [
    # Constants
    "COMMAND_PATTERN",
    "FORTUNE_PATTERN",
    "HTTP_TIMEOUT_SECONDS",
    # Enums
    "ApiType",
    "ContentMode",
    "SendMode",
    "MultiApiStrategy",
    "AccessControlMode",
    # Exceptions
    "SetuException",
    "ProviderError",
    "SendError",
    "AccessDeniedError",
    "ValidationError",
    "FortuneException",
    "FortuneNotFoundError",
    # Value Objects
    "SetuRequest",
    "AccessPolicy",
    "FortuneGenerationRequest",
    "FortuneRecord",
    "TagResolverService",
]
