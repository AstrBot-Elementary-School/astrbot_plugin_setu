from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from astrbot_plugin_setu.main import SetuPlugin


@pytest.mark.asyncio
async def test_initialize_uses_plugin_config_not_context_config(
    monkeypatch, tmp_path, sample_config_dict
) -> None:
    context = MagicMock()
    context.get_config.return_value = {
        "api": {
            "provider_overrides": [
                {"__template_key": "lolicon", "proxy": "wrong.example.com"}
            ]
        }
    }
    config = MagicMock()
    config.items.return_value = sample_config_dict.items()
    monkeypatch.setattr(
        "astrbot_plugin_setu.main.migrate_plugin_config", lambda *_args: None
    )

    plugin = SetuPlugin(context, config)
    plugin.name = "astrbot_plugin_setu"

    captured: dict[str, object] = {}

    def fake_init_config(raw_config):
        captured["raw_config"] = raw_config
        overrides = {
            item["__template_key"]: item
            for item in raw_config["api"]["provider_overrides"]
        }
        return MagicMock(
            api_type="lolicon",
            custom_api_configs=[],
            proxy=overrides["lolicon"]["proxy"],
            image_size="original",
            aspect_ratio="",
            uid=[],
            keyword="",
            cache_enabled=True,
            cache_ttl_hours=2,
            cache_max_items=200,
            cache_cleanup_on_start=True,
        )

    monkeypatch.setattr("astrbot_plugin_setu.main.init_config", fake_init_config)
    monkeypatch.setattr(
        "astrbot_plugin_setu.main.set_plugin_context", lambda _ctx: None
    )
    monkeypatch.setattr(
        "astrbot_plugin_setu.main.StarTools.get_data_dir", lambda _name: str(tmp_path)
    )
    monkeypatch.setattr(
        "astrbot_plugin_setu.main.init_provider_from_config", lambda _cfg: None
    )
    monkeypatch.setattr(
        "astrbot_plugin_setu.main.init_access_control_repo", AsyncMock()
    )
    monkeypatch.setattr("astrbot_plugin_setu.main.init_fortune_repo", AsyncMock())
    monkeypatch.setattr("astrbot_plugin_setu.main.init_send_cache", AsyncMock())
    monkeypatch.setattr("astrbot_plugin_setu.main.init_revoke_scheduler", AsyncMock())
    monkeypatch.setattr(
        "astrbot_plugin_setu.main.register_setu_llm_tools", lambda _handler: None
    )
    monkeypatch.setattr(
        "astrbot_plugin_setu.main.register_fortune_llm_tools", lambda: None
    )

    await plugin.initialize()

    raw_config = captured["raw_config"]
    assert isinstance(raw_config, dict)
    captured_overrides = {
        item["__template_key"]: item for item in raw_config["api"]["provider_overrides"]
    }
    expected_overrides = {
        item["__template_key"]: item
        for item in sample_config_dict["api"]["provider_overrides"]
    }
    assert (
        captured_overrides["lolicon"]["proxy"] == expected_overrides["lolicon"]["proxy"]
    )
