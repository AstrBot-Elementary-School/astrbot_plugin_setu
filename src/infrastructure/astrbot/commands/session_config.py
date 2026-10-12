"""Unified session configuration command and LLM tools."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from astrbot.api.event import AstrMessageEvent
from astrbot.core.provider.register import llm_tools

from ....application.session_config import (
    SESSION_CONFIG_KEYS,
    SessionConfigService,
    SessionConfigSnapshot,
    get_key_definition,
)
from ....application.session_config.keys import SessionConfigValidationError
from ...permission_service import PermissionService
from ...persistence import get_session_config_repo
from ..feature_switches import feature_enabled, require_feature
from ..session_identity import get_event_session_identity

LEGACY_CONFIG_TOOL_NAMES = (
    "get_setu_content_mode",
    "set_setu_content_mode",
    "set_setu_r18_docx_mode",
    "set_setu_auto_revoke",
    "set_setu_send_mode",
    "get_fortune_config",
    "set_fortune_config",
)


class SessionConfigCommandHandler:
    """Handles unified per-session configuration operations."""

    async def session_config_command(
        self, event: AstrMessageEvent, args: str = ""
    ) -> AsyncGenerator[Any, None]:
        """Handle `/session_config`."""
        args = (args or "").strip()
        if not args:
            async for result in self._handle_get(event, []):
                yield result
            return

        action = args.split(maxsplit=1)[0].lower()
        if action in ("get", "show", "status"):
            tail = args.split(maxsplit=1)[1] if " " in args else ""
            async for result in self._handle_get(event, tail.split()):
                yield result
            return
        if action == "set":
            async for result in self._handle_set(event, args):
                yield result
            return
        if action == "clear":
            async for result in self._handle_clear(event, args):
                yield result
            return

        yield event.plain_result(self._usage(f"未知子命令：{action}"))

    async def _handle_get(
        self, event: AstrMessageEvent, tokens: list[str]
    ) -> AsyncGenerator[Any, None]:
        try:
            key, as_json = _parse_get_tokens(tokens)
            snapshot = await _current_snapshot(event)
            if as_json:
                yield event.plain_result(_json(_snapshot_payload(snapshot, key)))
            elif key:
                yield event.plain_result(_format_one(snapshot, key))
            else:
                yield event.plain_result(_format_all(snapshot))
        except (RuntimeError, ValueError, SessionConfigValidationError) as exc:
            yield event.plain_result(str(exc))

    async def _handle_set(
        self, event: AstrMessageEvent, args: str
    ) -> AsyncGenerator[Any, None]:
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            yield event.plain_result(msg)
            return

        parts = args.split(maxsplit=2)
        if len(parts) < 3:
            yield event.plain_result(
                self._usage("用法：/session_config set <key> <value>")
            )
            return

        key = parts[1].strip()
        value = _strip_quotes(parts[2])
        try:
            service = SessionConfigService(get_session_config_repo())
            identity = get_event_session_identity(event)
            snapshot = await service.set_value(
                identity.session_id,
                identity.session_type,
                key,
                value,
                identity.display_name,
            )
            definition = get_key_definition(key)
            effective = snapshot.effective[key]
            yield event.plain_result(
                f"已设置 {definition.label}（{key}）为：{_format_value(effective)}"
            )
        except (RuntimeError, ValueError, SessionConfigValidationError) as exc:
            yield event.plain_result(str(exc))

    async def _handle_clear(
        self, event: AstrMessageEvent, args: str
    ) -> AsyncGenerator[Any, None]:
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            yield event.plain_result(msg)
            return

        parts = args.split(maxsplit=1)
        key = parts[1].strip() if len(parts) > 1 else None
        try:
            service = SessionConfigService(get_session_config_repo())
            identity = get_event_session_identity(event)
            await service.clear(
                identity.session_id,
                identity.session_type,
                key,
                identity.display_name,
            )
            if key:
                definition = get_key_definition(key)
                yield event.plain_result(
                    f"已清除 {definition.label}（{key}）的会话覆盖"
                )
            else:
                yield event.plain_result("已清除当前会话的全部配置覆盖")
        except (RuntimeError, ValueError, SessionConfigValidationError) as exc:
            yield event.plain_result(str(exc))

    @require_feature("llm_tools", "LLM 工具", "enabled")
    async def _llm_get_session_config(
        self, event: AstrMessageEvent, key: str = ""
    ) -> str:
        """LLM tool handler for reading current session config."""
        try:
            key = key.strip()
            if key:
                get_key_definition(key)
            snapshot = await _current_snapshot(event)
            return _json({"ok": True, "data": _snapshot_payload(snapshot, key or None)})
        except Exception as exc:
            return _json({"ok": False, "message": str(exc)})

    @require_feature("llm_tools", "LLM 工具", "enabled")
    async def _llm_set_session_config(
        self, event: AstrMessageEvent, key: str, value: str
    ) -> str:
        """LLM tool handler for setting current session config."""
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            return _json({"ok": False, "message": msg})
        try:
            normalized_key = key.strip()
            service = SessionConfigService(get_session_config_repo())
            identity = get_event_session_identity(event)
            snapshot = await service.set_value(
                identity.session_id,
                identity.session_type,
                normalized_key,
                value,
                identity.display_name,
            )
            return _json(
                {
                    "ok": True,
                    "message": "updated",
                    "key": normalized_key,
                    "value": snapshot.overrides[normalized_key],
                    "effective": snapshot.effective[normalized_key],
                }
            )
        except Exception as exc:
            return _json({"ok": False, "message": str(exc)})

    @require_feature("llm_tools", "LLM 工具", "enabled")
    async def _llm_clear_session_config(
        self, event: AstrMessageEvent, key: str = ""
    ) -> str:
        """LLM tool handler for clearing current session config."""
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            return _json({"ok": False, "message": msg})
        try:
            service = SessionConfigService(get_session_config_repo())
            identity = get_event_session_identity(event)
            normalized_key = key.strip() or None
            snapshot = await service.clear(
                identity.session_id,
                identity.session_type,
                normalized_key,
                identity.display_name,
            )
            return _json(
                {
                    "ok": True,
                    "message": "cleared",
                    "key": normalized_key,
                    "data": snapshot.to_dict(),
                }
            )
        except Exception as exc:
            return _json({"ok": False, "message": str(exc)})

    def _usage(self, prefix: str = "") -> str:
        lines = [
            prefix,
            "用法：",
            "/session_config get [key] [json]",
            "/session_config set <key> <value>",
            "/session_config clear [key]",
            "可用 key：",
            *[
                f"- {key}: {definition.label}"
                for key, definition in SESSION_CONFIG_KEYS.items()
            ],
        ]
        return "\n".join(line for line in lines if line)


async def _current_snapshot(event: AstrMessageEvent) -> SessionConfigSnapshot:
    service = SessionConfigService(get_session_config_repo())
    identity = get_event_session_identity(event)
    return await service.get_snapshot(
        identity.session_id,
        identity.session_type,
        identity.display_name,
    )


def _parse_get_tokens(tokens: list[str]) -> tuple[str | None, bool]:
    as_json = False
    cleaned: list[str] = []
    for token in tokens:
        if token.lower() == "json":
            as_json = True
        else:
            cleaned.append(token)
    if len(cleaned) > 1:
        raise ValueError("用法：/session_config get [key] [json]")
    key = cleaned[0] if cleaned else None
    if key:
        get_key_definition(key)
    return key, as_json


def _snapshot_payload(
    snapshot: SessionConfigSnapshot, key: str | None
) -> dict[str, Any]:
    if not key:
        return snapshot.to_dict()
    definition = get_key_definition(key)
    return {
        "session_id": snapshot.session_id,
        "session_type": snapshot.session_type,
        "display_name": snapshot.display_name,
        "key": key,
        "label": definition.label,
        "override": snapshot.overrides.get(key),
        "global": snapshot.global_values[key],
        "effective": snapshot.effective[key],
    }


def _format_all(snapshot: SessionConfigSnapshot) -> str:
    lines = [
        "当前会话配置",
        f"会话：{snapshot.display_name or snapshot.session_id} ({snapshot.session_type})",
        f"ID：{snapshot.session_id}",
        "",
    ]
    for key, definition in SESSION_CONFIG_KEYS.items():
        lines.append(f"{definition.label} ({key})")
        lines.append(f"  会话覆盖：{_format_override(snapshot.overrides, key)}")
        lines.append(f"  全局配置：{_format_value(snapshot.global_values[key])}")
        lines.append(f"  生效值：{_format_value(snapshot.effective[key])}")
    return "\n".join(lines)


def _format_one(snapshot: SessionConfigSnapshot, key: str) -> str:
    definition = get_key_definition(key)
    return "\n".join(
        [
            f"{definition.label} ({key})",
            f"会话覆盖：{_format_override(snapshot.overrides, key)}",
            f"全局配置：{_format_value(snapshot.global_values[key])}",
            f"生效值：{_format_value(snapshot.effective[key])}",
        ]
    )


def _format_override(overrides: dict[str, Any], key: str) -> str:
    if key not in overrides:
        return "未设置"
    return _format_value(overrides[key])


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "启用" if value else "禁用"
    if value == "":
        return "空"
    return str(value)


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def register_llm_tools() -> None:
    """Register unified session configuration LLM tools."""
    if not feature_enabled("llm_tools"):
        return
    _remove_tools(LEGACY_CONFIG_TOOL_NAMES)
    handler = SessionConfigCommandHandler()
    tools = [
        (
            "get_session_config",
            handler._llm_get_session_config,
            [
                {
                    "name": "key",
                    "type": "string",
                    "description": "Optional config key, e.g. setu.content_mode.",
                }
            ],
            "Get current session config as JSON.",
        ),
        (
            "set_session_config",
            handler._llm_set_session_config,
            [
                {"name": "key", "type": "string", "description": "Config key."},
                {"name": "value", "type": "string", "description": "Config value."},
            ],
            "Set one current-session config override as JSON result.",
        ),
        (
            "clear_session_config",
            handler._llm_clear_session_config,
            [
                {
                    "name": "key",
                    "type": "string",
                    "description": "Optional config key. Empty clears all overrides.",
                }
            ],
            "Clear current-session config override(s) as JSON result.",
        ),
    ]

    for name, handler_func, args, desc in tools:
        try:
            llm_tools.add_func(
                name=name, func_args=args, desc=desc, handler=handler_func
            )
            tool = llm_tools.get_func(name)
            if tool:
                tool.handler_module_path = __name__
        except (AttributeError, RuntimeError):
            pass


def unregister_llm_tools() -> None:
    """Unregister unified session configuration LLM tools."""
    _remove_tools(
        (
            "get_session_config",
            "set_session_config",
            "clear_session_config",
            *LEGACY_CONFIG_TOOL_NAMES,
        )
    )


def _remove_tools(names: tuple[str, ...]) -> None:
    for name in names:
        try:
            llm_tools.remove_func(name)
        except (AttributeError, RuntimeError):
            pass
