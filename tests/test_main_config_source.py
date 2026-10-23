from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from astrbot_plugin_setu.main import SetuPlugin


def test_conf_schema_exposes_sexnyan_and_platform_transport_templates() -> None:
    schema_path = Path(__file__).resolve().parents[1] / "_conf_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    delivery_items = schema["delivery"]["items"]
    assert "auto_revoke_r18" not in delivery_items
    assert delivery_items["auto_revoke_scope"]["default"] == "none"
    assert delivery_items["auto_revoke_scope"]["options"] == [
        "none",
        "sfw",
        "r18",
        "all",
    ]
    assert "doujinshi_file_cleanup_delay" not in delivery_items
    assert delivery_items["doujinshi_send_mode"]["default"] == "pdf"
    assert delivery_items["doujinshi_send_mode"]["options"] == [
        "pdf",
        "archive",
    ]
    assert delivery_items["doujinshi_max_page"]["default"] == 0
    assert delivery_items["auto_revoke_targets"]["default"] == ["doujinshi"]
    assert delivery_items["auto_revoke_targets"]["options"] == [
        "setu",
        "fortune",
        "doujinshi",
    ]
    assert delivery_items["auto_revoke_delay"]["default"] == 30

    transport_templates = delivery_items["platform_transports"]["templates"]
    napcat_items = transport_templates["napcat"]["items"]
    assert napcat_items["local_file_mode"]["default"] == "disabled"
    assert "stream_chunk_kb" not in napcat_items
    assert napcat_items["local_file_allowed_roots"]["default"] == []

    provider_templates = schema["api"]["items"]["provider_overrides"]["templates"]
    assert set(provider_templates["sexnyan"]["items"]) == {"proxy", "uid", "keyword"}

    assert "messages" not in schema
    assert "cache" not in schema
    assert set(schema["session_configs"]["templates"]) == {"setu", "fortune"}
    assert schema["safety"]["type"] == "template_list"
    assert len(schema["safety"]["templates"]) == 2


def test_setu_config_not_loaded_message_uses_resolver() -> None:
    source_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "infrastructure"
        / "astrbot"
        / "commands"
        / "setu.py"
    )
    source = source_path.read_text(encoding="utf-8")

    assert 'plain_result("配置未加载")' not in source
    assert 'self._message("config_not_loaded")' in source


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
            atri_proxy=overrides["atri"]["proxy"],
            atri_image_size="original",
            atri_aspect_ratio="",
            atri_uid=[],
            atri_keyword="",
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
        "astrbot_plugin_setu.main.register_setu_llm_tools", lambda: None
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
