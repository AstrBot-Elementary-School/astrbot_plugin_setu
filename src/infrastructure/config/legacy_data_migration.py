"""一次性将 Pages 的运行态设置迁入 AstrBot 插件配置。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from astrbot.core import AstrBotConfig
from pydantic import BaseModel, Field, field_validator, model_validator

from ...shared import get_logger
from ...shared.config.models import (
    AccessControlModeStr,
    SafetyConfig,
    SessionOverridesConfig,
    TriggerTemplateConfig,
)
from .legacy_migration import TRUE_VALUES, apply_legacy_config_aliases

MIGRATION_MARKER = "config_templates_migrated_v1"
_FALSE = {
    "0",
    "false",
    "no",
    "n",
    "off",
    "disable",
    "disabled",
    "关",
    "关闭",
    "禁用",
    "否",
}
_SETU_KEYS = {
    "setu.content_mode": "content_mode",
    "setu.send_mode": "send_mode",
    "setu.r18_docx": "r18_docx_mode",
    "setu.auto_revoke_scope": "auto_revoke_scope",
}
_FORTUNE_KEYS = {"fortune.content_mode": "content_mode", "fortune.tags": "tags"}


class LegacySafetyConfig(BaseModel):
    """Validate the obsolete user/group shape before refusing lossy conversion."""

    model_config = {"extra": "forbid"}

    setu_user_access_control_mode: AccessControlModeStr = AccessControlModeStr.NONE
    setu_group_access_control_mode: AccessControlModeStr = AccessControlModeStr.NONE
    setu_blocked_users: list[str] = Field(default_factory=list)
    setu_whitelist_users: list[str] = Field(default_factory=list)
    setu_blocked_groups: list[str] = Field(default_factory=list)
    setu_whitelist_groups: list[str] = Field(default_factory=list)
    fortune_user_access_control_mode: AccessControlModeStr = AccessControlModeStr.NONE
    fortune_group_access_control_mode: AccessControlModeStr = AccessControlModeStr.NONE
    fortune_blocked_users: list[str] = Field(default_factory=list)
    fortune_whitelist_users: list[str] = Field(default_factory=list)
    fortune_blocked_groups: list[str] = Field(default_factory=list)
    fortune_whitelist_groups: list[str] = Field(default_factory=list)

    @field_validator(
        "setu_blocked_users",
        "setu_whitelist_users",
        "setu_blocked_groups",
        "setu_whitelist_groups",
        "fortune_blocked_users",
        "fortune_whitelist_users",
        "fortune_blocked_groups",
        "fortune_whitelist_groups",
    )
    @classmethod
    def normalize_ids(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @model_validator(mode="after")
    def reject_conflicting_lists(self) -> LegacySafetyConfig:
        for feature in ("setu", "fortune"):
            for subject in ("users", "groups"):
                blocked = getattr(self, f"{feature}_blocked_{subject}")
                whitelist = getattr(self, f"{feature}_whitelist_{subject}")
                if set(blocked) & set(whitelist):
                    raise ValueError(f"{feature} {subject} 黑白名单不能包含相同 ID")
        return self


def _safety_templates(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        old = LegacySafetyConfig.model_validate(value).model_dump(mode="json")
        if any(
            item != "none" if key.endswith("_mode") else bool(item)
            for key, item in old.items()
        ):
            raise ValueError(
                "旧用户/群组权限无法推导完整 SID；请在插件配置 safety 中配置新的 SID 规则，原文件保持不变"
            )
        return []
    if isinstance(value, list) and any(
        isinstance(item, dict)
        and item.get("__template_key")
        in ("setu_user", "setu_group", "fortune_user", "fortune_group")
        for item in value
    ):
        old = {}
        seen = set()
        for item in value:
            key = item["__template_key"]
            if (
                key not in ("setu_user", "setu_group", "fortune_user", "fortune_group")
                or key in seen
            ):
                raise ValueError("旧访问控制模板非法或重复")
            if set(item) - {"__template_key", "mode", "blocked_ids", "whitelist_ids"}:
                raise ValueError("旧访问控制模板包含未知字段")
            seen.add(key)
            feature, subject = key.split("_")
            old[f"{key}_access_control_mode"] = item.get("mode", "none")
            old[f"{feature}_blocked_{subject}s"] = item.get("blocked_ids", [])
            old[f"{feature}_whitelist_{subject}s"] = item.get("whitelist_ids", [])
        return _safety_templates(old)
    return SafetyConfig.model_validate(value).model_dump(mode="json", by_alias=True)


def _bool(value: Any) -> bool:
    text = str(value).strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in _FALSE:
        return False
    raise ValueError(f"无法迁移布尔值：{value!r}")


def _read_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} 必须是 JSON object")
    return data


def _access_control(data: dict[str, Any]) -> dict[str, Any]:
    safety = LegacySafetyConfig().model_dump(mode="json")
    modes = data.get("modes", {})
    if not isinstance(modes, dict):
        raise TypeError("旧访问控制 modes 必须是 object")
    for key in safety:
        if key.endswith("_mode"):
            safety[key] = modes.get(key, safety[key])
    if "entries" not in data:
        for key in safety:
            if not key.endswith("_mode"):
                safety[key] = data.get(key, [])
    else:
        entries = data["entries"]
        if not isinstance(entries, list):
            raise ValueError("旧访问控制 entries 必须是 list")
        for entry in entries:
            feature = entry["feature"]
            subject = entry["subject_type"]
            kind = entry["list_type"]
            if (
                feature not in ("setu", "fortune")
                or subject not in ("user", "group")
                or kind not in ("blacklist", "whitelist")
            ):
                raise ValueError(f"无法迁移访问控制记录：{entry!r}")
            key = f"{feature}_{'blocked' if kind == 'blacklist' else 'whitelist'}_{subject}s"
            target_id = str(entry["target_id"]).strip()
            if not target_id:
                raise ValueError(f"访问控制记录缺少 ID：{entry!r}")
            safety[key].append(target_id)
    return LegacySafetyConfig.model_validate(safety).model_dump(mode="json")


def _legacy_templates(raw: dict[str, Any]) -> list[dict[str, Any]]:
    templates = []
    for section, feature in (
        ("session_configs", "setu"),
        ("fortune_session_configs", "fortune"),
    ):
        source = raw.get(section, [])
        if not isinstance(source, list):
            raise TypeError(f"{section} 必须是 list")
        for item in source:
            if "__template_key" in item:
                templates.append(dict(item))
                continue
            template = {"__template_key": feature, "session_id": item["session_id"]}
            keys = (
                ("content_mode", "send_mode", "r18_docx_mode", "auto_revoke_scope")
                if feature == "setu"
                else ("content_mode", "tags")
            )
            for key in keys:
                value = item.get(key, "")
                if value == "":
                    continue
                template[key] = (
                    str(_bool(value)).lower() if key == "r18_docx_mode" else value
                )
                if key == "tags":
                    template["override_tags"] = True
            if "auto_revoke_r18" in item and "auto_revoke_scope" not in template:
                template["auto_revoke_scope"] = (
                    "r18" if _bool(item["auto_revoke_r18"]) else "none"
                )
            templates.append(template)
    # 校验先于合并，避免重复条目被字典覆盖。
    SessionOverridesConfig(session_configs=templates)
    return templates


def _merge_sessions(
    templates: list[dict[str, Any]], data: dict[str, Any]
) -> list[dict[str, Any]]:
    sessions = data["sessions"]
    if not isinstance(sessions, list) or data.get("version", 1) != 1:
        raise ValueError("不支持的旧会话配置格式")
    by_key = {
        (item["session_id"].strip(), item["__template_key"]): dict(item)
        for item in templates
    }
    seen = set()
    for record in sessions:
        session_id = record["session_id"].strip()
        if not session_id or session_id in seen:
            raise ValueError(f"旧会话标识为空或重复：{session_id!r}")
        seen.add(session_id)
        overrides = record.get("overrides", {})
        if not isinstance(overrides, dict):
            raise TypeError(f"会话 {session_id} 的 overrides 必须是 object")
        overrides = dict(overrides)
        if "setu.auto_revoke" in overrides:
            value = overrides.pop("setu.auto_revoke")
            overrides.setdefault(
                "setu.auto_revoke_scope", "r18" if _bool(value) else "none"
            )
        for key, value in overrides.items():
            feature = "setu" if key in _SETU_KEYS else "fortune"
            field = (_SETU_KEYS | _FORTUNE_KEYS).get(key)
            if field is None:
                raise ValueError(f"无法迁移会话配置项：{key}")
            template = by_key.setdefault(
                (session_id, feature),
                {"__template_key": feature, "session_id": session_id},
            )
            template[field] = (
                str(_bool(value)).lower() if field == "r18_docx_mode" else value
            )
            if field == "tags":
                template["override_tags"] = True
    return list(by_key.values())


def migrate_plugin_config(data_dir: Path, config: AstrBotConfig) -> None:
    """持久化配置成功后才标记完成；失败时保留源文件并阻止启动。"""
    marker = data_dir / MIGRATION_MARKER
    original = dict(config.items())
    candidate = apply_legacy_config_aliases(deepcopy(original), [])
    general = candidate.get("setu_general", {})
    if "trigger_templates" in general:
        if not isinstance(general["trigger_templates"], list):
            raise ValueError("trigger_templates 必须是 list")
        for item in general["trigger_templates"]:
            TriggerTemplateConfig.model_validate(item)
    migrated_atri = general.get("api_type") == "atri"
    if migrated_atri:
        general["api_type"] = "lolicon"
    api = candidate.get("api", {})
    if isinstance(api, dict) and isinstance(api.get("provider_overrides"), list):
        api["provider_overrides"] = [
            item
            for item in api["provider_overrides"]
            if not isinstance(item, dict) or item.get("__template_key") != "atri"
        ]
    if marker.exists():
        if marker.read_text(encoding="utf-8") != "1":
            raise ValueError(f"迁移标记无效：{marker}")
    else:
        access_path = data_dir / "config.json"
        sessions_path = data_dir / "session_overrides.json"
        # Explicit SID policies let the operator replace legacy rules without deleting recovery data.
        safety = candidate.get("safety", [])
        has_sid_rules = (
            isinstance(safety, list)
            and bool(safety)
            and all(
                isinstance(rule, dict)
                and rule.get("__template_key") in ("setu", "fortune")
                for rule in safety
            )
        )
        if has_sid_rules:
            candidate["safety"] = _safety_templates(safety)
        elif access_path.exists():
            candidate["safety"] = _access_control(_read_object(access_path))
        templates = _legacy_templates(candidate)
        if sessions_path.exists():
            templates = _merge_sessions(templates, _read_object(sessions_path))
        candidate["session_configs"] = templates
        candidate.pop("fortune_session_configs", None)

    # 权限和会话非法值不能被通用 schema 自愈重置为宽松默认值。
    candidate["safety"] = _safety_templates(candidate.get("safety", []))
    sessions = SessionOverridesConfig.model_validate(candidate)
    candidate["session_configs"] = [
        item.model_dump(by_alias=True) for item in sessions.session_configs
    ]
    if candidate != original or not marker.exists():
        try:
            config.clear()
            config.update(candidate)
            config.save_config()
        except Exception:
            config.clear()
            config.update(original)
            raise
        if not marker.exists():
            data_dir.mkdir(parents=True, exist_ok=True)
            temporary = marker.with_suffix(".tmp")
            temporary.write_text("1", encoding="utf-8")
            temporary.replace(marker)

    if migrated_atri:
        get_logger().warning(
            "Atri 图片源已移除，已将 api_type=atri 保存为 lolicon；随机本子仍使用 Atri 服务"
        )
