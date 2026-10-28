"""LLM 发送失败回归。"""

from unittest.mock import MagicMock

import pytest
from astrbot_plugin_setu.src.infrastructure.astrbot.commands import SetuCommandHandler


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
