"""Resolve session templates over global settings without persistence."""

from __future__ import annotations

from dataclasses import dataclass

from ...shared.config.models import SetuPluginConfig


@dataclass(frozen=True)
class SessionSettings:
    content_mode: str
    send_mode: str
    r18_docx_mode: bool
    auto_revoke_scope: str
    fortune_content_mode: str
    fortune_tags: str


class SessionConfigService:
    """Read the validated template matching the complete session identity."""

    def __init__(self, config: SetuPluginConfig) -> None:
        self._config = config

    def resolve(self, session_id: str | None) -> SessionSettings:
        config = self._config
        values = {
            "content_mode": config.content_mode,
            "send_mode": config.send_mode,
            "r18_docx_mode": config.r18_docx_mode,
            "auto_revoke_scope": config.auto_revoke_scope,
            "fortune_content_mode": config.fortune.content_mode.value,
            "fortune_tags": config.fortune.tags,
        }
        for item in config.session_configs:
            if item.session_id != session_id:
                continue
            if item.template_key == "setu":
                for key in ("content_mode", "send_mode", "auto_revoke_scope"):
                    value = getattr(item, key)
                    if value != "inherit":
                        values[key] = value
                if item.r18_docx_mode != "inherit":
                    values["r18_docx_mode"] = item.r18_docx_mode == "true"
            else:
                if item.content_mode != "inherit":
                    values["fortune_content_mode"] = item.content_mode
                if item.override_tags:
                    values["fortune_tags"] = item.tags
        return SessionSettings(**values)
