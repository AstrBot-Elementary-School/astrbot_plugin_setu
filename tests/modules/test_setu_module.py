"""Tests for SetuModule class."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from astrbot_plugin_setu.src.infrastructure.astrbot.commands import (
    SessionConfigCommandHandler,
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


class TestSessionConfigCommandHandler:
    """Test unified session config adapter initialization."""

    def test_module_has_required_methods(self) -> None:
        """Test command adapter methods exist."""
        handler = SessionConfigCommandHandler()

        assert hasattr(handler, "session_config_command")
        assert hasattr(handler, "_llm_get_session_config")
        assert hasattr(handler, "_llm_set_session_config")
        assert hasattr(handler, "_llm_clear_session_config")


@pytest.mark.asyncio
async def test_llm_reports_docx_failure(
    tmp_path, mock_event, sample_config_dict, monkeypatch
):
    from unittest.mock import AsyncMock

    from astrbot_plugin_setu.src.application.setu import ImagePayload
    from astrbot_plugin_setu.src.infrastructure.astrbot.commands import setu
    from astrbot_plugin_setu.src.infrastructure.sending.image_sender import ImageSender
    from astrbot_plugin_setu.src.shared.config import SetuPluginConfig

    context = MagicMock()
    context.send_message = AsyncMock()
    handler = SetuCommandHandler(tmp_path, plugin_context=context)
    handler._check_access = AsyncMock(return_value=(True, ""))
    handler._get_effective_content_mode = AsyncMock(return_value="r18")
    handler._message = lambda key: key
    monkeypatch.setattr(
        setu, "get_config", lambda: SetuPluginConfig(**sample_config_dict)
    )
    monkeypatch.setattr(setu, "init_provider_from_config", lambda _: None)
    provider = MagicMock()
    provider.fetch_and_download = AsyncMock(
        return_value=ImagePayload(
            urls=(), raw_bytes=(b"test",), file_paths=(), r18=True, tags=()
        )
    )
    monkeypatch.setattr(setu, "get_provider", lambda: provider)
    failure = mock_event.plain_result("docx failed")

    async def failed_send(self, payload, event):
        assert self._docx_service is handler._docx_service
        yield failure

    monkeypatch.setattr(ImageSender, "send_images", failed_send)
    assert await handler._llm_get_setu_handler(mock_event) == "send_failed"
    context.send_message.assert_awaited_once_with(
        mock_event.unified_msg_origin, failure
    )
