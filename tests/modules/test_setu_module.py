"""Tests for SetuModule class."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from astrbot_plugin_setu.src.infrastructure.astrbot.commands import (
    SetuCommandHandler,
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


class TestSetuCommandHandler:
    """Test Setu command adapter initialization."""

    def test_module_init(self, mock_plugin_context, mock_config) -> None:
        """Test handler initialization."""
        handler = SetuCommandHandler()
        assert handler is not None

    def test_module_has_required_methods(
        self, mock_plugin_context, mock_config
    ) -> None:
        """Test module has required methods."""
        handler = SetuCommandHandler()

        assert hasattr(handler, "get_random_picture")
        assert hasattr(handler, "setu_command")
        assert hasattr(handler, "_get_effective_content_mode")
        assert callable(handler.get_random_picture)
        assert callable(handler.setu_command)

    def test_module_has_decorators(self, mock_plugin_context, mock_config) -> None:
        """Test command adapter methods exist."""
        handler = SetuCommandHandler()

        assert hasattr(handler, "setu_command")
        assert hasattr(handler, "_fetch_and_send_images")
