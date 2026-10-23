"""Persisted-format and user-data preservation guarantees for config migration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from astrbot.core import AstrBotConfig
from astrbot_plugin_setu.main import SetuPlugin
from astrbot_plugin_setu.src.infrastructure.config.legacy_data_migration import (
    MIGRATION_MARKER,
    migrate_plugin_config,
)
from pydantic import ValidationError


def make_config(tmp_path: Path, values=None) -> AstrBotConfig:
    return AstrBotConfig(str(tmp_path / "plugin.json"), default_config=values or {})


def write_legacy(tmp_path: Path) -> tuple[str, str]:
    access = json.dumps(
        {
            "modes": {"setu_user_access_control_mode": "whitelist"},
            "entries": [
                {
                    "feature": "setu",
                    "subject_type": "user",
                    "list_type": "whitelist",
                    "target_id": "allowed",
                }
            ],
            "setu_whitelist_users": ["stale"],
        }
    )
    sessions = json.dumps(
        {
            "version": 1,
            "sessions": [
                {
                    "session_id": "bot:GroupMessage:123",
                    "session_type": "group",
                    "display_name": "群",
                    "overrides": {
                        "setu.content_mode": "r18",
                        "setu.r18_docx": False,
                        "setu.auto_revoke": True,
                        "fortune.tags": "",
                        "fortune.content_mode": "sfw",
                    },
                }
            ],
        }
    )
    (tmp_path / "config.json").write_text(access)
    (tmp_path / "session_overrides.json").write_text(sessions)
    return access, sessions


def test_migrates_both_stores_once_and_preserves_sources(tmp_path) -> None:
    sources = write_legacy(tmp_path)
    config = make_config(
        tmp_path,
        {
            "safety": [
                {
                    "__template_key": "setu",
                    "mode": "whitelist",
                    "whitelist_sids": ["bot:GroupMessage:123"],
                }
            ],
            "session_configs": [
                {
                    "__template_key": "setu",
                    "session_id": "bot:GroupMessage:123",
                    "content_mode": "sfw",
                    "send_mode": "forward",
                }
            ],
        },
    )
    migrate_plugin_config(tmp_path, config)
    persisted = json.loads((tmp_path / "plugin.json").read_text(encoding="utf-8-sig"))
    assert persisted["safety"][0]["whitelist_sids"] == ["bot:GroupMessage:123"]
    setu, fortune = persisted["session_configs"]
    assert setu["content_mode"] == "r18"
    assert setu["send_mode"] == "forward"
    assert setu["r18_docx_mode"] == "false"
    assert setu["auto_revoke_scope"] == "r18"
    assert fortune["override_tags"] is True and fortune["tags"] == ""
    assert (tmp_path / MIGRATION_MARKER).read_text() == "1"
    assert (tmp_path / "config.json").read_text() == sources[0]
    assert (tmp_path / "session_overrides.json").read_text() == sources[1]

    # 模拟用户在插件配置中删除模板、清空白名单后重启。
    config["safety"][0]["whitelist_sids"] = []
    config["session_configs"] = []
    config.save_config()
    reloaded = make_config(tmp_path, dict(config))
    migrate_plugin_config(tmp_path, reloaded)
    assert reloaded["safety"][0]["mode"] == "whitelist"
    assert reloaded["safety"][0]["whitelist_sids"] == []
    assert reloaded["session_configs"] == []


def test_legacy_flat_templates_are_converted(tmp_path) -> None:
    config = make_config(
        tmp_path,
        {
            "session_configs": [
                {
                    "session_id": "old",
                    "session_type": "group",
                    "auto_revoke_r18": True,
                    "r18_docx_mode": "false",
                }
            ],
            "fortune_session_configs": [{"session_id": "old", "tags": "猫耳"}],
        },
    )
    migrate_plugin_config(tmp_path, config)
    assert config["session_configs"][0]["auto_revoke_scope"] == "r18"
    assert config["session_configs"][1]["override_tags"] is True
    assert "fortune_session_configs" not in config


@pytest.mark.parametrize(
    "filename,content",
    [
        ("config.json", "{broken"),
        ("config.json", '{"modes":{"setu_user_access_control_mode":"invalid"}}'),
        (
            "session_overrides.json",
            '{"sessions":[{"session_id":"a","overrides":{"setu.content_mode":"invalid"}}]}',
        ),
    ],
)
def test_invalid_source_blocks_without_writing_config(
    tmp_path, filename, content
) -> None:
    (tmp_path / filename).write_text(content)
    config = make_config(tmp_path)
    before = (tmp_path / "plugin.json").read_text(encoding="utf-8-sig")
    with pytest.raises((ValueError, KeyError)):
        migrate_plugin_config(tmp_path, config)
    assert not (tmp_path / MIGRATION_MARKER).exists()
    assert (tmp_path / "plugin.json").read_text(encoding="utf-8-sig") == before


def test_save_failure_does_not_mark_or_change_memory(tmp_path, monkeypatch) -> None:
    write_legacy(tmp_path)
    (tmp_path / "config.json").write_text("{}")
    config = make_config(tmp_path)
    monkeypatch.setattr(
        AstrBotConfig, "save_config", MagicMock(side_effect=OSError("disk full"))
    )
    with pytest.raises(OSError, match="disk full"):
        migrate_plugin_config(tmp_path, config)
    assert dict(config) == {}
    assert not (tmp_path / MIGRATION_MARKER).exists()


def test_marker_failure_surfaces_and_retry_is_idempotent(tmp_path, monkeypatch) -> None:
    write_legacy(tmp_path)
    (tmp_path / "config.json").write_text("{}")
    config = make_config(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", MagicMock(side_effect=OSError("marker failed")))
        with pytest.raises(OSError, match="marker failed"):
            migrate_plugin_config(tmp_path, config)
    saved = dict(config)
    assert not (tmp_path / MIGRATION_MARKER).exists()
    migrate_plugin_config(tmp_path, config)
    assert dict(config) == saved


@pytest.mark.asyncio
async def test_initialization_stops_before_provider_on_migration_error(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "config.json").write_text("broken")
    config = make_config(tmp_path)
    plugin = SetuPlugin(MagicMock(), config)
    plugin.name = "astrbot_plugin_setu"
    provider = MagicMock()
    monkeypatch.setattr(
        "astrbot_plugin_setu.main.StarTools.get_data_dir", lambda _: tmp_path
    )
    monkeypatch.setattr("astrbot_plugin_setu.main.init_provider_from_config", provider)
    with pytest.raises(ValueError):
        await plugin.initialize()
    provider.assert_not_called()


def test_completed_migration_rejects_invalid_current_permissions(tmp_path) -> None:
    config = make_config(tmp_path)
    migrate_plugin_config(tmp_path, config)
    config["safety"] = {"setu_user_access_control_mode": "bad"}
    with pytest.raises(ValidationError):
        migrate_plugin_config(tmp_path, config)
    assert config["safety"]["setu_user_access_control_mode"] == "bad"


def test_old_permissions_require_explicit_sid_replacement(tmp_path) -> None:
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "_conf_schema.json").read_text()
    )
    config = make_config(tmp_path, {"safety": {"setu_blocked_users": ["blocked"]}})
    (tmp_path / MIGRATION_MARKER).write_text("1")
    reloaded = AstrBotConfig(config.config_path, schema=schema)
    before = Path(config.config_path).read_text()
    with pytest.raises(ValueError, match="完整 SID"):
        migrate_plugin_config(tmp_path, reloaded)
    assert Path(config.config_path).read_text() == before
    reloaded["safety"] = [
        {
            "__template_key": "setu",
            "mode": "blacklist",
            "blocked_sids": ["bot:GroupMessage:123"],
        }
    ]
    migrate_plugin_config(tmp_path, reloaded)
    reloaded["safety"] = []
    reloaded.save_config()
    migrate_plugin_config(tmp_path, reloaded)
    assert reloaded["safety"] == []


def test_old_pages_ids_do_not_silently_grant_access(tmp_path) -> None:
    sources = write_legacy(tmp_path)
    config = make_config(tmp_path)
    with pytest.raises(ValueError, match="完整 SID"):
        migrate_plugin_config(tmp_path, config)
    assert dict(config) == {}
    assert not (tmp_path / MIGRATION_MARKER).exists()
    assert (tmp_path / "config.json").read_text() == sources[0]
    assert (tmp_path / "session_overrides.json").read_text() == sources[1]


@pytest.mark.parametrize("mode,blocked", [("none", ["123"]), ("whitelist", [])])
def test_previous_dimension_templates_do_not_lose_permissions(
    tmp_path, mode, blocked
) -> None:
    config = make_config(
        tmp_path,
        {
            "safety": [
                {"__template_key": "setu_group", "mode": mode, "blocked_ids": blocked}
            ]
        },
    )
    (tmp_path / MIGRATION_MARKER).write_text("1")
    with pytest.raises(ValueError, match="完整 SID"):
        migrate_plugin_config(tmp_path, config)
    assert config["safety"][0]["__template_key"] == "setu_group"


@pytest.mark.parametrize(
    "old,new,expected",
    [
        ("always", None, "always"),
        ("never", None, "never"),
        ("always", "fallback", "fallback"),
        (None, None, "fallback"),
    ],
)
def test_card_migration_survives_native_schema_loading(
    tmp_path, old, new, expected
) -> None:
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "_conf_schema.json").read_text()
    )
    values = {}
    if old is not None:
        values["html_card"] = {"strategy": old}
    if new is not None:
        values["delivery"] = {"html_card_strategy": new}
    config = make_config(tmp_path, values)
    reloaded = AstrBotConfig(config.config_path, schema=schema)
    migrate_plugin_config(tmp_path, reloaded)
    assert reloaded["delivery"]["html_card_strategy"] == expected
    assert "html_card" not in reloaded
    again = AstrBotConfig(config.config_path, schema=schema)
    migrate_plugin_config(tmp_path, again)
    assert again["delivery"]["html_card_strategy"] == expected
    assert "html_card" not in again


def test_invalid_card_migration_does_not_overwrite_source(tmp_path) -> None:
    config = make_config(tmp_path, {"html_card": {"strategy": "invalid"}})
    before = (tmp_path / "plugin.json").read_text()
    with pytest.raises(ValueError):
        migrate_plugin_config(tmp_path, config)
    assert (tmp_path / "plugin.json").read_text() == before
    assert config["html_card"]["strategy"] == "invalid"
    assert not (tmp_path / MIGRATION_MARKER).exists()
