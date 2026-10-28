"""Session identity and content/delivery boundaries must remain isolated."""

from __future__ import annotations

import pytest
from astrbot_plugin_setu.src.application.session_config import SessionConfigService
from astrbot_plugin_setu.src.infrastructure.astrbot.commands.setu import (
    SetuCommandHandler,
)
from astrbot_plugin_setu.src.infrastructure.sending.image_sender import ImageSender
from astrbot_plugin_setu.src.shared.config.models import SetuPluginConfig
from pydantic import ValidationError


def configured() -> SetuPluginConfig:
    return SetuPluginConfig(
        fortune={"tags": "全局"},
        session_configs=[
            {
                "__template_key": "setu",
                "session_id": "bot:GroupMessage:123",
                "content_mode": "r18",
                "send_mode": "forward",
                "r18_docx_mode": "false",
                "auto_revoke_scope": "all",
            },
            {
                "__template_key": "fortune",
                "session_id": "bot:GroupMessage:123",
                "content_mode": "r18",
                "override_tags": True,
                "tags": "",
            },
        ],
    )


def test_exact_session_matching_and_explicit_empty_tags() -> None:
    service = SessionConfigService(configured())
    selected = service.resolve("bot:GroupMessage:123")
    assert selected.content_mode == "r18" and selected.send_mode == "forward"
    assert selected.r18_docx_mode is False and selected.auto_revoke_scope == "all"
    assert selected.fortune_tags == "" and selected.fortune_content_mode == "r18"
    for other in (None, "123", "other:GroupMessage:123", "bot:FriendMessage:123"):
        inherited = service.resolve(other)
        assert inherited.content_mode == "sfw"
        assert inherited.fortune_tags == "全局"
    config = configured()
    config.session_configs[1].override_tags = False
    assert (
        SessionConfigService(config).resolve("bot:GroupMessage:123").fortune_tags
        == "全局"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"content_mode": "bad"},
        {"send_mode": "bad"},
        {"r18_docx_mode": "bad"},
        {"session_id": " "},
    ],
)
def test_invalid_overrides_rejected(change) -> None:
    with pytest.raises(ValidationError):
        SetuPluginConfig(
            session_configs=[
                {"__template_key": "setu", "session_id": "session", **change}
            ]
        )


def test_duplicate_templates_rejected() -> None:
    template = {"__template_key": "setu", "session_id": "session"}
    with pytest.raises(ValidationError, match="重复"):
        SetuPluginConfig(session_configs=[template, template])


@pytest.mark.asyncio
async def test_request_and_sender_apply_same_session_settings(
    mock_event, monkeypatch
) -> None:
    config = configured()
    mock_event.unified_msg_origin = "bot:GroupMessage:123"
    monkeypatch.setattr(
        "astrbot_plugin_setu.src.infrastructure.astrbot.commands.setu.get_config",
        lambda: config,
    )
    assert await SetuCommandHandler()._get_effective_content_mode(mock_event) == "r18"
    options = await ImageSender(config)._build_options(mock_event, is_r18=True)
    assert options.send_mode == "forward"
    assert options.r18_docx_mode is False
    assert options.auto_revoke_scope == "all"


def test_inherit_keeps_global_booleans() -> None:
    config = SetuPluginConfig(
        delivery={"r18_docx_mode": False},
        session_configs=[{"__template_key": "setu", "session_id": "x"}],
    )
    assert SessionConfigService(config).resolve("x").r18_docx_mode is False
