"""Read-only access policies from plugin configuration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain.access_control.value_objects import AccessPolicy


class AccessControlRepository(ABC):
    @abstractmethod
    def get_policy(self, feature: str) -> AccessPolicy:
        """Return the feature's complete SID policy."""
        ...
