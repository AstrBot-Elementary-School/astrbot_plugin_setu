from __future__ import annotations

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
