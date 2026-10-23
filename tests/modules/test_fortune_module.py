"""Tests for FortuneModule class."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from astrbot_plugin_setu.src.infrastructure.astrbot.commands import (
    FortuneCommandHandler,
)


@pytest.fixture
def mock_plugin_context() -> MagicMock:
    """Create mock AstrBot plugin context."""
    context = MagicMock()
    context.get_config = MagicMock(return_value={})
    context.logger = MagicMock()
    return context


@pytest.fixture
def mock_config() -> MagicMock:
    """Create mock AstrBot config."""
    config = MagicMock()
    config.__getitem__ = MagicMock(return_value={})
    config.get = MagicMock(return_value=None)
    return config


class TestFortuneCommandHandler:
    """Test Fortune command adapter initialization."""

    def test_module_init(self, mock_plugin_context, mock_config) -> None:
        """Test handler initialization."""
        handler = FortuneCommandHandler()
        assert handler is not None

    def test_module_has_required_methods(
        self, mock_plugin_context, mock_config
    ) -> None:
        """Test module has required methods."""
        handler = FortuneCommandHandler()

        assert hasattr(handler, "fortune_command")
        assert hasattr(handler, "refresh_fortune_command")
        assert callable(handler.fortune_command)
        assert callable(handler.refresh_fortune_command)

    def test_module_has_decorators(self, mock_plugin_context, mock_config) -> None:
        """Test command adapter methods exist."""
        handler = FortuneCommandHandler()

        assert hasattr(handler, "refresh_group_fortune_command")
        assert hasattr(handler, "refresh_all_fortune_command")
        assert not hasattr(handler, "enable_fortune_group_command")
        assert not hasattr(handler, "disable_fortune_group_command")
