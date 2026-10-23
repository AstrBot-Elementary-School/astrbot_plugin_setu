from __future__ import annotations

import pytest
from astrbot_plugin_setu.src.infrastructure.config import heal_astrbot_plugin_config
from astrbot_plugin_setu.src.shared.config import (
    SetuPluginConfig,
    should_auto_revoke,
)
from pydantic import ValidationError


def test_provider_config_accepts_empty_aspect_ratio(sample_config_dict) -> None:
    config = SetuPluginConfig(**sample_config_dict)

    assert config.aspect_ratio == ""
    assert config.atri_aspect_ratio == ""


def test_auto_revoke_scope_defaults_to_none() -> None:
    config = SetuPluginConfig()

    assert config.auto_revoke_scope == "none"
    assert config.auto_revoke_setu_enabled is False
    assert config.auto_revoke_fortune_enabled is False
    assert config.auto_revoke_doujinshi_enabled is True
    assert should_auto_revoke(config.auto_revoke_scope, is_r18=False) is False
    assert should_auto_revoke(config.auto_revoke_scope, is_r18=True) is False


def test_doujinshi_send_mode_defaults_to_pdf_and_accepts_archive() -> None:
    assert SetuPluginConfig().doujinshi_send_mode == "pdf"
    assert (
        SetuPluginConfig(
            delivery={"doujinshi_send_mode": "archive"}
        ).doujinshi_send_mode
        == "archive"
    )


def test_doujinshi_max_page_defaults_to_zero_and_accepts_value() -> None:
    assert SetuPluginConfig().doujinshi_max_page == 0
    assert (
        SetuPluginConfig(delivery={"doujinshi_max_page": 11}).doujinshi_max_page == 11
    )


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


def test_legacy_message_objects_do_not_change_builtin_text() -> None:
    config = SetuPluginConfig(
        messages={
            "fetch_failed": {"enabled": True},
            "revoke_scheduled": {"enabled": True},
        }
    )

    assert config.resolve_message("fetch_failed") == "获取图片失败，请稍后再试"
    assert (
        config.resolve_message("revoke_scheduled", revoke_delay=30)
        == "已设置自动撤回，将在 30 秒后撤回。"
    )


def test_doujinshi_messages_ignore_legacy_overrides() -> None:
    config = SetuPluginConfig(messages={"doujinshi_fetching": {"enabled": True}})

    assert (
        config.resolve_message("doujinshi_fetching")
        == "正在获取随机本子并生成文件，请稍候..."
    )
    assert (
        config.resolve_message("doujinshi_failed")
        == "随机本子获取或文件生成失败，请稍后再试。"
    )


def test_resolve_message_supports_placeholders(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["messages"] = {
        **sample_config_dict.get("messages", {}),
        "max_count_exceeded": {
            "enabled": True,
            "text": "一次最多只能获取{max_count}张哦~",
        },
    }
    config = SetuPluginConfig(**config_dict)

    text = config.resolve_message("max_count_exceeded", max_count=7)

    assert text == "一次最多只能获取7张哦~"


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


def test_resolve_message_supports_dotted_builtin_error_keys(
    sample_config_dict,
) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["messages"] = {
        **sample_config_dict.get("messages", {}),
        "error_invalid_request": {"enabled": True, "text": "请求参数无效"},
    }
    config = SetuPluginConfig(**config_dict)

    assert config.resolve_message("error.invalid_request") == "请求参数无效"


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


def test_delivery_napcat_transport_defaults(sample_config_dict) -> None:
    config = SetuPluginConfig(**sample_config_dict)

    assert config.napcat_local_file_mode == "disabled"
    assert config.napcat_local_file_allowed_roots == []
    assert config.napcat_stream_chunk_kb == 64


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


def test_sexnyan_provider_template_override(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["api"] = {
        **sample_config_dict["api"],
        "provider_overrides": [
            {
                "__template_key": "sexnyan",
                "proxy": "pixiv-proxy.example.com",
                "uid": [1001, 1002],
                "keyword": "blue",
            }
        ],
    }
    config = SetuPluginConfig(**config_dict)

    assert config.sexnyan_proxy == "pixiv-proxy.example.com"
    assert config.sexnyan_uid == [1001, 1002]
    assert config.sexnyan_keyword == "blue"


def test_exclude_ai_uses_atri_override_when_api_type_is_atri(
    sample_config_dict,
) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["setu_general"] = {
        **sample_config_dict["setu_general"],
        "api_type": "atri",
    }
    config_dict["api"] = {
        **sample_config_dict["api"],
        "provider_overrides": [
            {
                "__template_key": "lolicon",
                "image_size": "original",
                "proxy": "",
                "aspect_ratio": "",
                "uid": [],
                "keyword": "",
                "exclude_ai": True,
            },
            {
                "__template_key": "atri",
                "image_size": "original",
                "proxy": "",
                "aspect_ratio": "",
                "uid": [],
                "keyword": "",
                "exclude_ai": False,
            },
        ],
    }
    config = SetuPluginConfig(**config_dict)

    assert config.exclude_ai is False


def test_tag_alias_templates_override_text_default(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["setu_general"] = {
        **sample_config_dict["setu_general"],
        "tag_alias_templates": [
            {
                "__template_key": "alias",
                "canonical": "少女",
                "aliases": ["girl", "girls"],
            }
        ],
    }
    config = SetuPluginConfig(**config_dict)

    assert config.tag_alias == "少女=girl,girls"


def test_legacy_auto_handle_send_failure_is_ignored(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["delivery"] = {
        **sample_config_dict["delivery"],
        "auto_handle_send_failure": False,
    }

    config = SetuPluginConfig(**config_dict)

    assert not hasattr(config.delivery, "auto_handle_send_failure")


def test_retired_source_options_do_not_affect_runtime() -> None:
    config = SetuPluginConfig(
        setu_general={"multi_api_strategy": "random"}, fortune={"api_type": "atri"}
    )
    assert not hasattr(config.setu_general, "multi_api_strategy")
    assert not hasattr(config.fortune, "api_type")
    assert not hasattr(config, "fortune_api_type")
    assert config.html_card_strategy == "fallback"


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


def test_schema_layout_and_no_emoji_markers() -> None:
    import json
    import re
    from pathlib import Path

    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "_conf_schema.json").read_text()
    )
    assert [
        item["description"] for item in schema.values() if not item.get("invisible")
    ] == [
        "图片获取",
        "发送与撤回",
        "今日运势",
        "会话设置",
        "访问控制",
        "图片来源高级设置",
    ]
    assert schema["setu_general"]["items"]["tag_alias_templates"]["condition"] == {
        "show_advanced": True
    }
    assert schema["delivery"]["items"]["compress_max_mb"]["condition"] == {
        "compress_enabled": True,
        "show_advanced": True,
    }
    assert schema["fortune"]["items"]["tags"]["condition"] == {"enabled": True}
    assert schema["session_configs"]["templates"]["fortune"]["items"]["tags"][
        "condition"
    ] == {"override_tags": True}
    for rule in schema["safety"]["templates"].values():
        assert rule["items"]["blocked_sids"]["condition"] == {"mode": "blacklist"}
        assert rule["items"]["whitelist_sids"]["condition"] == {"mode": "whitelist"}
    text = json.dumps(schema, ensure_ascii=False)
    assert "obvious_hint" not in text
    assert not re.search("[\U0001f000-\U0001faff\u2600-\u27bf\u203c\ufe0f]", text)
