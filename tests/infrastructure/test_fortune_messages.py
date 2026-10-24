from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from astrbot_plugin_setu.src.infrastructure.astrbot.commands import (
    fortune as fortune_cmd,
)
from astrbot_plugin_setu.src.infrastructure.astrbot.commands.fortune import (
    FortuneCommandHandler,
)
from astrbot_plugin_setu.src.shared.config import SetuPluginConfig


def test_fortune_message_ignores_legacy_template(
    monkeypatch, sample_config_dict
) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["messages"] = {
        **sample_config_dict.get("messages", {}),
        "fortune_refresh_group_done": {
            "enabled": True,
            "text": "本群已刷新 {count} 条运势",
        },
    }
    config = SetuPluginConfig(**config_dict)
    monkeypatch.setattr(
        "astrbot_plugin_setu.src.infrastructure.astrbot.commands.fortune.get_config",
        lambda: config,
    )

    handler = FortuneCommandHandler()
    assert (
        handler._message("fortune_refresh_group_done", count=3)
        == "已刷新本群 3 位用户的今日运势"
    )


def test_fortune_message_ignores_legacy_disabled_flag(
    monkeypatch, sample_config_dict
) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["messages"] = {
        **sample_config_dict.get("messages", {}),
        "fortune_group_only": {"enabled": False, "text": "X"},
    }
    config = SetuPluginConfig(**config_dict)
    monkeypatch.setattr(
        "astrbot_plugin_setu.src.infrastructure.astrbot.commands.fortune.get_config",
        lambda: config,
    )

    handler = FortuneCommandHandler()
    assert handler._message("fortune_group_only") == "此命令仅支持群聊"


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["command", "tool"])
@pytest.mark.parametrize(
    "outcome", ["success", "pending", "failed", "exception", "no_image"]
)
async def test_fortune_delivery_and_text_fallback(
    monkeypatch, mock_event, entry, outcome
):
    config = SetuPluginConfig()
    record = SimpleNamespace(
        title="小吉",
        star_count=3,
        max_stars=7,
        date_str="2026-10-23",
        description="测试运势",
    )
    service = SimpleNamespace(get_or_create_fortune=AsyncMock(return_value=record))
    monkeypatch.setattr(fortune_cmd, "get_config", lambda: config)
    monkeypatch.setattr(fortune_cmd, "get_fortune_repo", lambda: object())
    monkeypatch.setattr(fortune_cmd, "FortuneService", lambda **kwargs: service)
    payloads = []
    completed = []

    class Sender:
        def __init__(self, cfg, logger, *, content_type):
            assert cfg is config and content_type == "fortune"

        async def send_images(self, payload, event):
            payloads.append(payload)
            if outcome == "exception":
                raise RuntimeError("transport failed")
            if outcome == "failed":
                yield event.plain_result("generic image failure")
            else:
                yield {"send_success": True, "send_pending": outcome == "pending"}
            completed.append(True)

    monkeypatch.setattr(fortune_cmd, "ImageSender", Sender)
    handler = FortuneCommandHandler()
    handler._check_access = AsyncMock(return_value=(True, ""))
    handler._build_fortune_request = MagicMock(return_value=object())
    handler._render_fortune_image = AsyncMock(
        return_value=None if outcome == "no_image" else b"card"
    )
    mock_event.plain_result.side_effect = lambda text: text
    if entry == "command":
        result = [value async for value in handler.fortune_command(mock_event)]
        text = "".join(result)
    else:
        text = await handler._llm_get_fortune(mock_event)
    handler._render_fortune_image.assert_awaited_once()
    mock_event.chain_result.assert_not_called()
    if outcome == "no_image":
        assert payloads == []
    else:
        assert payloads[0].raw_bytes == (b"card",)
    if outcome in ("success", "pending"):
        assert completed == [True]
        if entry == "command":
            assert text == ""
        else:
            assert "已提交今日运势图" in text
    else:
        assert "运势图未能发送" in text and "小吉" in text
        assert "generic image failure" not in text
