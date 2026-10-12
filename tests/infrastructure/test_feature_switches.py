"""Feature gates exercised through actual AstrBot plugin module imports."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from astrbot_plugin_setu.src.infrastructure.astrbot import feature_switches
from astrbot_plugin_setu.src.infrastructure.astrbot.commands import (
    fortune,
    session_config,
    setu,
)
from astrbot_plugin_setu.src.shared.config.models import SetuPluginConfig


@pytest.fixture
def disabled_config(monkeypatch):
    config = SetuPluginConfig(
        doujinshi={"enabled": False},
        llm_tools={"enabled": False},
        fortune={"enabled": False},
    )
    monkeypatch.setattr(feature_switches, "get_config", lambda: config)
    return config


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler,method",
    [
        (setu.SetuCommandHandler, "random_doujinshi_command"),
        (fortune.FortuneCommandHandler, "fortune_command"),
        (fortune.FortuneCommandHandler, "refresh_fortune_command"),
        (fortune.FortuneCommandHandler, "enable_fortune_group_command"),
    ],
)
async def test_disabled_command_does_not_touch_event_state(
    disabled_config, handler, method
):
    event = SimpleNamespace(plain_result=lambda text: text)
    instance = object.__new__(handler)
    replies = [result async for result in getattr(instance, method)(event)]
    assert len(replies) == 1
    assert "关闭" in replies[0]


@pytest.mark.parametrize("module", [setu, fortune, session_config])
def test_disabled_tools_do_not_register(disabled_config, monkeypatch, module):
    registry = MagicMock()
    monkeypatch.setattr(module, "llm_tools", registry)
    module.register_llm_tools()
    registry.add_func.assert_not_called()


@pytest.mark.asyncio
async def test_session_command_available_when_llm_disabled(disabled_config):
    handler = session_config.SessionConfigCommandHandler()

    async def get_config(event, tokens):
        assert tokens == ["content_mode"]
        yield "session config"

    handler._handle_get = get_config
    replies = [
        result
        async for result in handler.session_config_command(object(), "get content_mode")
    ]
    assert replies == ["session config"]


def test_schema_group_order_and_removed_switch():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "_conf_schema.json").read_text(encoding="utf-8"))
    assert list(schema)[:4] == ["setu_general", "doujinshi", "llm_tools", "triggers"]
    assert "session_config" not in schema
    config = SetuPluginConfig(session_config={"command_enabled": False})
    assert "session_config" not in config.model_dump()
