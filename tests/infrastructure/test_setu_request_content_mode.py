"""验证单次 R18 标记从命令输入传到图片请求，不修改配置。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot_plugin_setu.src.infrastructure.astrbot.commands import setu
from astrbot_plugin_setu.src.shared.config.models import SetuPluginConfig


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("natural", "text", "count", "tags", "mode", "expected_r18"),
    [
        (False, "", "1", "girl r18", "mix", True),
        (False, "", "r18", "", "r18", True),
        (False, "", "girl", "r18", "mix", True),
        (False, "", "1", "girl", "sfw", False),
        (False, "", "1", "girl", "r18", True),
        (True, "来一张girl色图 r18", "", "", "mix", True),
        (True, "来一张girl r18 色图", "", "", "r18", True),
        (True, "来一张girl色图", "", "", "sfw", False),
        (True, "来一张girl色图", "", "", "r18", True),
    ],
)
async def test_command_request_content_mode(
    monkeypatch, mock_event, natural, text, count, tags, mode, expected_r18
):
    config = SimpleNamespace(max_count=10, tag_alias="少女=girl", content_mode=mode)
    monkeypatch.setattr(setu, "get_config", lambda: config)
    handler = setu.SetuCommandHandler()
    handler._check_access = AsyncMock(return_value=(True, ""))
    handler._get_effective_content_mode = AsyncMock(return_value=mode)
    requests = []

    async def fetch(event, num, parsed_tags, r18, cfg):
        requests.append((num, parsed_tags, r18))
        yield "sent"

    monkeypatch.setattr(handler, "_fetch_and_send_images", fetch)
    mock_event.message_str = text
    if natural:
        result = [x async for x in handler._handle_random_picture_internal(mock_event)]
    else:
        result = [
            x
            async for x in handler._handle_setu_command_internal(
                mock_event, count, tags
            )
        ]
    assert result == ["sent"]
    expected_tags = [] if count == "r18" else ["少女"]
    assert requests == [(1, expected_tags, expected_r18)]
    assert config.content_mode == mode


@pytest.mark.asyncio
async def test_r18_marker_preserves_access_control(monkeypatch, mock_event):
    monkeypatch.setattr(setu, "get_config", lambda: SimpleNamespace(max_count=10))
    handler = setu.SetuCommandHandler()
    handler._check_access = AsyncMock(return_value=(False, "禁止访问"))
    handler._get_effective_content_mode = AsyncMock()
    _ = [x async for x in handler._handle_setu_command_internal(mock_event, "1", "r18")]
    handler._get_effective_content_mode.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["r18", "mix"])
async def test_llm_request_r18_marker(monkeypatch, mock_event, mode):
    from astrbot_plugin_setu.src.infrastructure import sending
    from astrbot_plugin_setu.src.infrastructure.astrbot import feature_switches

    config = SimpleNamespace(
        tag_alias="少女=girl", exclude_ai=True, max_replenish_rounds=3
    )
    monkeypatch.setattr(setu, "get_config", lambda: config)
    monkeypatch.setattr(feature_switches, "feature_enabled", lambda *args: True)
    monkeypatch.setattr(setu, "init_provider_from_config", lambda config: None)
    provider = SimpleNamespace(
        fetch_and_download=AsyncMock(return_value=SimpleNamespace(count=1))
    )
    monkeypatch.setattr(setu, "get_provider", lambda: provider)

    class Sender:
        async def send_images(self, payload, event):
            yield "sent"

    monkeypatch.setattr(sending, "ImageSender", lambda *args: Sender())
    handler = setu.SetuCommandHandler()
    handler._check_access = AsyncMock(return_value=(True, ""))
    handler._get_effective_content_mode = AsyncMock(return_value=mode)
    result = await handler._llm_get_setu_handler(
        mock_event, tags=["blue archive", "r18", "girl"]
    )
    assert result == "Successfully fetched 1 images"
    request = provider.fetch_and_download.call_args.args[0]
    assert request.r18 is True
    assert request.tags == ("blue archive", "少女")


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["command", "natural", "llm"])
@pytest.mark.parametrize("global_mode", ["sfw", "r18", "mix"])
@pytest.mark.parametrize("silent", [False, True])
async def test_effective_sfw_blocks_marker_before_provider(
    monkeypatch, mock_event, entry, global_mode, silent
):
    from astrbot_plugin_setu.src.infrastructure.astrbot import feature_switches

    config = SetuPluginConfig(
        setu_general={"content_mode": global_mode},
        messages={
            "message_overrides": [
                {
                    "message_key": "r18_not_allowed",
                    "enabled": not silent,
                    "text": "拒绝 R18",
                }
            ]
        },
    )
    monkeypatch.setattr(setu, "get_config", lambda: config)
    monkeypatch.setattr(feature_switches, "get_config", lambda: config)
    monkeypatch.setattr(
        setu,
        "get_event_session_identity",
        lambda event: SimpleNamespace(
            session_id="test", session_type="group", display_name="test"
        ),
    )
    service = SimpleNamespace(get_effective_value=AsyncMock(return_value="sfw"))
    monkeypatch.setattr(setu, "get_session_config_repo", lambda: object())
    monkeypatch.setattr(setu, "SessionConfigService", lambda repo: service)
    init_provider = AsyncMock()
    get_provider = AsyncMock()
    monkeypatch.setattr(setu, "init_provider_from_config", init_provider)
    monkeypatch.setattr(setu, "get_provider", get_provider)
    handler = setu.SetuCommandHandler()
    handler._check_access = AsyncMock(return_value=(True, ""))
    mock_event.plain_result.side_effect = lambda text: text
    if entry == "command":
        results = [
            x
            async for x in handler._handle_setu_command_internal(mock_event, "1", "r18")
        ]
    elif entry == "natural":
        mock_event.message_str = "来一张色图 r18"
        results = [x async for x in handler._handle_random_picture_internal(mock_event)]
    else:
        reply = await handler._llm_get_setu_handler(mock_event, tags=["r18"])
        results = [reply] if reply else []
    assert results == ([] if silent else ["拒绝 R18"])
    init_provider.assert_not_called()
    get_provider.assert_not_called()
    assert config.content_mode == global_mode
    assert service.get_effective_value.await_count == 1


@pytest.mark.parametrize("mode", ["sfw", "", "unknown"])
def test_r18_marker_fails_closed_for_modes_without_r18(mode):
    assert setu.SetuCommandHandler._resolve_request_r18(mode, True) is None


@pytest.mark.parametrize("random_value,expected", [(0.1, False), (0.9, True)])
def test_mix_mode_without_marker_preserves_random_choice(
    monkeypatch, random_value, expected
):
    monkeypatch.setattr(setu.random, "random", lambda: random_value)
    assert setu.SetuCommandHandler._resolve_request_r18("mix", False) is expected
