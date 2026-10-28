"""Feature opt-outs and the per-request content boundary must precede I/O."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from astrbot_plugin_setu import main
from astrbot_plugin_setu.src.infrastructure.astrbot.commands import setu, fortune
from astrbot_plugin_setu.src.shared.config import SetuPluginConfig


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["command", "natural", "tool"])
@pytest.mark.parametrize("session_sfw", [False, True])
async def test_r18_refused_before_provider_access(
    monkeypatch, mock_event, entry, session_sfw
):
    cfg = SetuPluginConfig(
        setu_general={"content_mode": "mix" if session_sfw else "sfw"},
        session_configs=[
            {
                "__template_key": "setu",
                "session_id": mock_event.unified_msg_origin,
                "content_mode": "sfw",
            }
        ]
        if session_sfw
        else [],
    )
    monkeypatch.setattr(setu, "get_config", lambda: cfg)
    provider = MagicMock(side_effect=AssertionError("must not request provider"))
    monkeypatch.setattr(setu, "init_provider_from_config", provider)
    handler = setu.SetuCommandHandler()
    handler._check_access = AsyncMock(return_value=(True, ""))
    mock_event.plain_result.side_effect = lambda text: text
    if entry == "tool":
        output = await handler._llm_get_setu_handler(mock_event, tags=["r18", "girl"])
    else:
        output = "".join(
            [
                x
                async for x in handler.setu_command(
                    mock_event, "1", tags="girl R18", natural=entry == "natural"
                )
            ]
        )
    assert "SFW" in output
    provider.assert_not_called()


@pytest.mark.asyncio
async def test_disabled_features_do_not_touch_services(
    monkeypatch, mock_event, tmp_path
):
    cfg = SetuPluginConfig(
        fortune={"enabled": False},
        delivery={"doujinshi_enabled": False},
        setu_general={"llm_tools_enabled": False},
    )
    monkeypatch.setattr(setu, "get_config", lambda: cfg)
    monkeypatch.setattr(fortune, "get_config", lambda: cfg)
    renderer = MagicMock(side_effect=AssertionError("must not initialize renderer"))
    monkeypatch.setattr(fortune, "FortuneRenderer", renderer)
    repo = MagicMock(side_effect=AssertionError("must not access fortune data"))
    monkeypatch.setattr(fortune, "get_fortune_repo", repo)
    mock_event.plain_result.side_effect = lambda text: text
    handler = fortune.FortuneCommandHandler()
    for name in [
        "fortune_command",
        "refresh_fortune_command",
        "refresh_group_fortune_command",
        "refresh_all_fortune_command",
    ]:
        assert "已停用" in "".join(
            [x async for x in getattr(handler, name)(mock_event)]
        )
    for name in [
        "_llm_get_fortune",
        "_llm_refresh_fortune",
        "_llm_refresh_group_fortune",
        "_llm_refresh_all_fortune",
    ]:
        assert "已停用" in await getattr(handler, name)(mock_event)
    assert await handler.pregenerate_active_fortune_images() == 0
    cfg.fortune.enabled = True
    for name in [
        "_llm_get_fortune",
        "_llm_refresh_fortune",
        "_llm_refresh_group_fortune",
        "_llm_refresh_all_fortune",
    ]:
        assert "LLM 工具已停用" in await getattr(handler, name)(mock_event)
    image_handler = setu.SetuCommandHandler(tmp_path)
    image_handler._check_access = AsyncMock(return_value=(True, ""))
    image_handler._doujinshi_service.fetch_random_file = AsyncMock()
    assert "已停用" in "".join(
        [x async for x in image_handler.random_doujinshi_command(mock_event)]
    )
    image_handler._doujinshi_service.fetch_random_file.assert_not_awaited()
    assert "已停用" in await image_handler._llm_get_setu_handler(mock_event)
    renderer.assert_not_called()
    repo.assert_not_called()
    tools = MagicMock()
    monkeypatch.setattr(setu, "llm_tools", tools)
    monkeypatch.setattr(fortune, "llm_tools", tools)
    setu.register_llm_tools()
    fortune.register_llm_tools()
    tools.add_func.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "allow,access,expected",
    [(True, True, True), (False, True, False), (True, False, False)],
)
async def test_self_refresh_requires_opt_in_and_sid_access(
    monkeypatch, mock_event, allow, access, expected
):
    cfg = SetuPluginConfig(fortune={"allow_user_refresh": allow})
    monkeypatch.setattr(fortune, "get_config", lambda: cfg)
    monkeypatch.setattr(
        fortune.PermissionService, "require_admin", lambda _: (False, "admin required")
    )
    handler = fortune.FortuneCommandHandler()
    handler._check_access = AsyncMock(return_value=(access, "denied"))
    assert (await handler._check_self_refresh(mock_event))[0] is expected


@pytest.mark.asyncio
async def test_disabled_fortune_still_restores_revoke_queue(monkeypatch, tmp_path):
    cfg = SetuPluginConfig(
        fortune={"enabled": False}, setu_general={"llm_tools_enabled": False}
    )
    plugin = main.SetuPlugin(MagicMock(), MagicMock())
    plugin.name = "astrbot_plugin_setu"
    monkeypatch.setattr(main.StarTools, "get_data_dir", lambda _: tmp_path)
    monkeypatch.setattr(main, "migrate_plugin_config", lambda *_: None)
    monkeypatch.setattr(plugin, "_heal_runtime_plugin_config", lambda _: {})
    monkeypatch.setattr(main, "init_config", lambda _: cfg)
    monkeypatch.setattr(main, "init_provider_from_config", MagicMock())
    monkeypatch.setattr(main, "init_access_control_repo", AsyncMock())
    monkeypatch.setattr(main, "init_send_cache", AsyncMock())
    fortune_init = AsyncMock()
    revokes = AsyncMock()
    monkeypatch.setattr(main, "init_fortune_repo", fortune_init)
    monkeypatch.setattr(main, "init_revoke_scheduler", revokes)
    await plugin.initialize()
    fortune_init.assert_not_awaited()
    revokes.assert_awaited_once_with(tmp_path, plugin.context)
    assert plugin._fortune_pregenerate_task is None


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["command", "natural", "tool"])
async def test_r18_is_request_only_and_not_a_provider_tag(
    monkeypatch, mock_event, entry
):
    cfg = SetuPluginConfig(
        setu_general={
            "content_mode": "mix",
            "natural_language_enabled": entry == "natural",
        }
    )
    monkeypatch.setattr(setu, "get_config", lambda: cfg)
    handler = setu.SetuCommandHandler()
    handler._check_access = AsyncMock(return_value=(True, ""))
    if entry == "tool":
        monkeypatch.setattr(setu, "init_provider_from_config", lambda _: None)
        provider = MagicMock()
        provider.fetch_and_download = AsyncMock(
            side_effect=RuntimeError("recorded request")
        )
        monkeypatch.setattr(setu, "get_provider", lambda: provider)
        await handler._llm_get_setu_handler(mock_event, tags=["white hair", "R18"])
        request = provider.fetch_and_download.await_args.args[0]
        assert request.tags == ("white hair",) and request.r18 is True
    else:
        captured = []

        async def fetch(event, num, tags, r18, config):
            captured.append((num, tags, r18))
            if False:
                yield None

        monkeypatch.setattr(handler, "_fetch_and_send_images", fetch)
        if entry == "natural":
            monkeypatch.setattr(main, "get_config", lambda: cfg)
            mock_event.message_str = "来二份girl色图 r18"
            results = [
                x async for x in main._route_regex_command(mock_event, handler, None)
            ]
        else:
            results = [
                x async for x in handler.setu_command(mock_event, "2", tags="girl r18")
            ]
        assert results == []
        assert captured == [(2, ["少女"], True)]
    assert cfg.content_mode == "mix"
