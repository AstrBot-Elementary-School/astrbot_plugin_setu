from __future__ import annotations

import pytest
from astrbot_plugin_setu.src.infrastructure.config import heal_astrbot_plugin_config
from astrbot_plugin_setu.src.shared.config import (
    SetuPluginConfig,
    should_auto_revoke,
)
from pydantic import ValidationError


def test_auto_revoke_scope_defaults_to_none() -> None:
    config = SetuPluginConfig()

    assert config.auto_revoke_scope == "none"
    assert config.auto_revoke_setu_enabled is False
    assert config.auto_revoke_fortune_enabled is False
    assert config.auto_revoke_doujinshi_enabled is True
    assert should_auto_revoke(config.auto_revoke_scope, is_r18=False) is False
    assert should_auto_revoke(config.auto_revoke_scope, is_r18=True) is False


def test_auto_revoke_delay_and_targets_are_configured_independently() -> None:
    config = SetuPluginConfig(
        delivery={
            "auto_revoke_delay": 1800,
            "auto_revoke_targets": ["setu", "fortune"],
        }
    )

    assert config.auto_revoke_delay == 1800
    assert config.doujinshi_file_cleanup_delay == 1800
    assert config.auto_revoke_setu_enabled is True
    assert config.auto_revoke_fortune_enabled is True
    assert config.auto_revoke_doujinshi_enabled is False
    assert SetuPluginConfig(delivery={"auto_revoke_delay": 0}).auto_revoke_delay == 0


def test_auto_revoke_scope_validation(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["delivery"] = {
        **sample_config_dict["delivery"],
        "auto_revoke_scope": "all",
    }

    config = SetuPluginConfig(**config_dict)

    assert config.auto_revoke_scope == "all"
    assert should_auto_revoke("sfw", is_r18=False) is True
    assert should_auto_revoke("sfw", is_r18=True) is False
    assert should_auto_revoke("r18", is_r18=False) is False
    assert should_auto_revoke("r18", is_r18=True) is True
    assert should_auto_revoke("all", is_r18=False) is True
    assert should_auto_revoke("all", is_r18=True) is True

    invalid = sample_config_dict.copy()
    invalid["delivery"] = {
        **sample_config_dict["delivery"],
        "auto_revoke_scope": "bad",
    }
    with pytest.raises(ValidationError):
        SetuPluginConfig(**invalid)


def test_only_failure_messages_are_builtin() -> None:
    config = SetuPluginConfig()

    for key in (
        "fetching",
        "found",
        "revoke_scheduled",
        "doujinshi_fetching",
        "fortune_image_submitted",
        "fortune_refresh_group_done",
        "fortune_refresh_all_done",
    ):
        assert config.resolve_message(key) is None
    assert (
        config.resolve_message("invalid_count", min_count=1, max_count=7)
        == "数量解析失败，图片数量必须在1-7之间"
    )


def test_config_healer_migrates_legacy_auto_revoke_scope() -> None:
    schema = {
        "delivery": {
            "type": "object",
            "items": {
                "auto_revoke_scope": {
                    "type": "string",
                    "default": "none",
                    "options": ["none", "sfw", "r18", "all"],
                }
            },
        }
    }
    healed, changes = heal_astrbot_plugin_config(
        {"delivery": {"auto_revoke_r18": True}}, schema
    )

    assert healed["delivery"] == {"auto_revoke_scope": "r18"}
    assert changes

    healed, _ = heal_astrbot_plugin_config(
        {"delivery": {"auto_revoke_r18": False}}, schema
    )
    assert healed["delivery"] == {"auto_revoke_scope": "none"}

    healed, _ = heal_astrbot_plugin_config(
        {"delivery": {"auto_revoke_r18": "是"}}, schema
    )
    assert healed["delivery"] == {"auto_revoke_scope": "r18"}


def test_config_healer_keeps_new_auto_revoke_scope_when_legacy_exists() -> None:
    schema = {
        "delivery": {
            "type": "object",
            "items": {
                "auto_revoke_scope": {
                    "type": "string",
                    "default": "none",
                    "options": ["none", "sfw", "r18", "all"],
                }
            },
        }
    }
    healed, changes = heal_astrbot_plugin_config(
        {"delivery": {"auto_revoke_r18": True, "auto_revoke_scope": "all"}},
        schema,
    )

    assert healed["delivery"] == {"auto_revoke_scope": "all"}
    assert changes


def test_config_healer_migrates_legacy_doujinshi_cleanup_delay() -> None:
    schema = {
        "delivery": {
            "type": "object",
            "items": {"auto_revoke_delay": {"type": "int", "default": 30}},
        }
    }

    healed, changes = heal_astrbot_plugin_config(
        {"delivery": {"doujinshi_file_cleanup_delay": 1800}}, schema
    )

    assert healed["delivery"] == {"auto_revoke_delay": 1800}
    assert changes

    healed, changes = heal_astrbot_plugin_config(
        {
            "delivery": {
                "auto_revoke_delay": 45,
                "doujinshi_file_cleanup_delay": 1800,
            }
        },
        schema,
    )
    assert healed["delivery"] == {"auto_revoke_delay": 45}
    assert changes


def test_provider_template_override_takes_precedence(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["api"] = {
        **sample_config_dict["api"],
        "provider_overrides": [
            {
                "__template_key": "lolicon",
                "image_size": "regular",
                "proxy": "pixiv.example.test",
                "aspect_ratio": "vertical",
                "uid": [123],
                "keyword": "blue",
                "exclude_ai": False,
            }
        ],
    }
    config = SetuPluginConfig(**config_dict)

    assert config.image_size == "regular"
    assert config.proxy == "pixiv.example.test"
    assert config.aspect_ratio == "vertical"
    assert config.uid == [123]
    assert config.keyword == "blue"
    assert config.exclude_ai is False


def test_delivery_platform_transport_template_takes_precedence(
    sample_config_dict,
) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["delivery"] = {
        **sample_config_dict["delivery"],
        "platform_transports": [
            {
                "__template_key": "napcat",
                "stream_mode": "always",
                "stream_chunk_kb": 512,
                "local_file_mode": "fallback",
                "local_file_allowed_roots": ["/AstrBot/data"],
            }
        ],
        "napcat_stream_mode": "disabled",
        "napcat_stream_chunk_kb": 64,
        "napcat_local_file_mode": "disabled",
        "napcat_local_file_allowed_roots": [],
    }
    config = SetuPluginConfig(**config_dict)

    assert config.napcat_stream_mode == "always"
    assert config.napcat_stream_chunk_kb == 64
    assert config.napcat_local_file_mode == "fallback"
    assert config.napcat_local_file_allowed_roots == ["/AstrBot/data"]


def test_delivery_legacy_napcat_fields_remain_supported(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["delivery"] = {
        **sample_config_dict["delivery"],
        "napcat_stream_mode": "disabled",
        "napcat_stream_chunk_kb": 256,
        "napcat_local_file_mode": "always",
        "napcat_local_file_allowed_roots": ["/legacy/shared"],
    }
    config = SetuPluginConfig(**config_dict)

    assert config.napcat_stream_mode == "disabled"
    assert config.napcat_stream_chunk_kb == 64
    assert config.napcat_local_file_mode == "always"
    assert config.napcat_local_file_allowed_roots == ["/legacy/shared"]


def test_layout_conditions_preserve_hidden_values() -> None:
    import json
    from pathlib import Path

    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "_conf_schema.json").read_text()
    )
    raw = {
        "delivery": {"compress_enabled": False, "compress_max_mb": 9},
        "fortune": {"enabled": False, "tags": "少女", "auto_refresh": False},
        "safety": [
            {
                "__template_key": "setu",
                "mode": "blacklist",
                "blocked_sids": ["bot:GroupMessage:123"],
                "whitelist_sids": ["bot:GroupMessage:456"],
            }
        ],
        "session_configs": [
            {
                "__template_key": "fortune",
                "session_id": "bot:GroupMessage:123",
                "override_tags": False,
                "tags": "可爱",
            }
        ],
    }
    healed, _ = heal_astrbot_plugin_config(raw, schema)
    config = SetuPluginConfig(**healed)
    assert config.compress_max_mb == 9
    assert config.fortune.tags == "少女"
    assert not config.fortune.auto_refresh
    assert config.safety.root[0].whitelist_sids == ["bot:GroupMessage:456"]
    assert config.session_configs[0].tags == "可爱"
    assert config.html_card_strategy == "fallback"
    assert "html_card" not in healed
