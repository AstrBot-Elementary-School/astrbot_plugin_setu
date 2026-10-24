"""Fortune command handler - all Fortune-related commands."""

from __future__ import annotations

import base64
import random
from collections.abc import AsyncGenerator
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent
from astrbot.core.provider.register import llm_tools

from ....application.session_config import SessionConfigService
from ....application.setu import ImagePayload
from ....domain.access_control.service import AccessControlService
from ....domain.fortune import (
    FortuneGenerationRequest,
    FortuneRecord,
)
from ....domain.fortune.service import FortuneService
from ....domain.setu import SetuRequest
from ....shared import get_logger
from ... import get_access_control_repo, get_provider
from ...permission_service import PermissionService
from ...persistence import get_fortune_repo
from ...providers import init_provider_from_config
from ...sending import DirectSendStrategy, ImageSender, schedule_revoke
from ...sending.platform_capabilities import is_onebot_like_platform
from ..config import get_config, get_plugin_context
from ..fortune_renderer import FortuneRenderer
from ..session_identity import get_event_session_identity

logger = get_logger()

# Regex pattern directly in decorator (not in constants)
FORTUNE_REGEX_PATTERN = r"^(?!/)(今日运势|jrys)$"


class FortuneCommandHandler:
    """Handles all Fortune-related commands.

    Uses singleton pattern for config, fortune repo, and access control repo.
    Commands are auto-registered by AstrBot decorators.
    """

    def __init__(self) -> None:
        self._renderer = FortuneRenderer()

    # ==================== Command Handlers ====================

    async def fortune_command(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[Any, None]:
        """Handle /今日运势 command (/今日运势, /jrys)."""
        config = get_config()
        if not config:
            if result := self._plain(event, self._message("config_not_loaded")):
                yield result
            return

        has_perm, msg = await self._check_access(event, config)
        if not has_perm:
            if result := self._plain(event, msg):
                yield result
            return

        request = self._build_fortune_request(event)

        try:
            repo = get_fortune_repo()
            service = FortuneService(repository=repo)
            result = await service.get_or_create_fortune(request)
            if await self._send_fortune_image(event, result, service, config):
                return
            text = self._message(
                "fortune_image_failed", fortune=self._format_fortune(result)
            )
            if await self._send_fortune_with_auto_revoke(
                event, [Comp.Plain(text)], config
            ):
                return
            yield event.plain_result(text)
        except Exception as e:
            text = self._message("fortune_get_failed", error=e)
            if result := self._plain(event, text):
                yield result

    async def _send_fortune_image(
        self,
        event: AstrMessageEvent,
        record: FortuneRecord,
        service: FortuneService,
        config: Any,
    ) -> bool:
        """Share image delivery across commands and tools; uncertain receipts must not trigger duplicates."""
        try:
            image = await self._render_fortune_image(record, service)
            if not image:
                return False
            payload = ImagePayload(urls=(), raw_bytes=(image,), r18=False, tags=())
            sender = ImageSender(config, logger, content_type="fortune")
            sent = False
            async for result in sender.send_images(payload, event):
                if isinstance(result, dict) and result.get("send_success"):
                    sent = True
            # The caller supplies the text fortune instead of the generic image-failure notice.
            return sent
        except Exception:
            logger.exception("[fortune] image delivery failed; falling back to text")
            return False

    async def _send_fortune_with_auto_revoke(
        self,
        event: AstrMessageEvent,
        chain: list[Any],
        config: Any,
    ) -> bool:
        """在启用且支持的情况下发送今日运势并登记可恢复撤回任务。"""
        if not getattr(config, "auto_revoke_fortune_enabled", False):
            return False
        if config.auto_revoke_delay <= 0:
            return False

        platform_name = getattr(getattr(event, "platform", None), "name", None)
        if not is_onebot_like_platform(platform_name):
            return False

        plugin_context = get_plugin_context()
        if plugin_context is None:
            logger.warning("[fortune] 自动撤回已启用但插件上下文未初始化")
            return False

        send_result = await DirectSendStrategy(plugin_context).send_with_status(
            event, chain, auto_revoke=True
        )
        if not send_result.accepted:
            return False
        if not send_result.message_ids:
            logger.warning("[fortune] 发送成功但未返回 message_id，无法登记自动撤回")
            return True

        scheduled = 0
        for message_id in send_result.message_ids:
            if await schedule_revoke(event, message_id, config.auto_revoke_delay):
                scheduled += 1
        if scheduled == 0:
            logger.warning("[fortune] 未能登记今日运势自动撤回任务")
        return True

    async def refresh_fortune_command(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[Any, None]:
        """Handle /刷新今日运势 command."""
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            if result := self._plain(event, msg):
                yield result
            return

        config = get_config()
        if not config:
            if result := self._plain(event, self._message("config_not_loaded")):
                yield result
            return

        request = self._build_fortune_request(event)

        try:
            repo = get_fortune_repo()
            service = FortuneService(repository=repo)
            result = await service.refresh_fortune(request)
            yield event.plain_result(self._format_fortune(result))
        except Exception as e:
            text = self._message("fortune_refresh_failed", error=e)
            if result := self._plain(event, text):
                yield result

    async def refresh_group_fortune_command(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[Any, None]:
        """Handle /刷新本群今日运势 command."""
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            if result := self._plain(event, msg):
                yield result
            return

        group_id = event.get_group_id()
        if not group_id:
            if result := self._plain(event, self._message("fortune_group_only")):
                yield result
            return

        config = get_config()
        if not config:
            if result := self._plain(event, self._message("config_not_loaded")):
                yield result
            return

        try:
            repo = get_fortune_repo()
            service = FortuneService(repository=repo)
            refreshed_count = await service.pregenerate_active_users()
            text = self._message("fortune_refresh_group_done", count=refreshed_count)
            if result := self._plain(event, text):
                yield result
        except Exception as e:
            text = self._message("fortune_refresh_group_failed", error=e)
            if result := self._plain(event, text):
                yield result

    async def refresh_all_fortune_command(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[Any, None]:
        """Handle /刷新全局今日运势 command."""
        has_perm, msg = PermissionService.require_super_user(event)
        if not has_perm:
            if result := self._plain(event, msg):
                yield result
            return

        config = get_config()
        if not config:
            if result := self._plain(event, self._message("config_not_loaded")):
                yield result
            return

        try:
            repo = get_fortune_repo()
            service = FortuneService(repository=repo)
            refreshed_count = await service.pregenerate_active_users()
            text = self._message("fortune_refresh_all_done", count=refreshed_count)
            if result := self._plain(event, text):
                yield result
        except Exception as e:
            text = self._message("fortune_refresh_all_failed", error=e)
            if result := self._plain(event, text):
                yield result

    # ==================== LLM Tool Handlers ====================

    async def _llm_get_fortune(self, event: AstrMessageEvent) -> str:
        """LLM tool handler for getting today's fortune."""
        config = get_config()
        if not config:
            return self._message("config_not_loaded")

        has_perm, msg = await self._check_access(event, config)
        if not has_perm:
            return msg

        request = self._build_fortune_request(event)

        try:
            repo = get_fortune_repo()
            service = FortuneService(repository=repo)
            result = await service.get_or_create_fortune(request)
            sent = await self._send_fortune_image(event, result, service, config)
            return self._message(
                "fortune_image_submitted" if sent else "fortune_image_failed",
                fortune=self._format_fortune(result),
            )
        except Exception as e:
            return self._message("fortune_get_failed", error=e)

    async def _llm_refresh_fortune(self, event: AstrMessageEvent) -> str:
        """LLM tool handler for refreshing today's fortune."""
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            return msg

        config = get_config()
        if not config:
            return self._message("config_not_loaded")

        request = self._build_fortune_request(event)

        try:
            repo = get_fortune_repo()
            service = FortuneService(repository=repo)
            result = await service.refresh_fortune(request)
            return f"今日运势已刷新: {result.title}"
        except Exception as e:
            return self._message("fortune_refresh_failed", error=e)

    async def _llm_refresh_group_fortune(self, event: AstrMessageEvent) -> str:
        """LLM tool handler for refreshing group fortunes."""
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            return msg

        group_id = event.get_group_id()
        if not group_id:
            return self._message("fortune_group_only")

        config = get_config()
        if not config:
            return self._message("config_not_loaded")

        try:
            repo = get_fortune_repo()
            service = FortuneService(repository=repo)
            refreshed_count = await service.pregenerate_active_users()
            return self._message("fortune_refresh_group_done", count=refreshed_count)
        except Exception as e:
            return self._message("fortune_refresh_group_failed", error=e)

    async def _llm_refresh_all_fortune(self, event: AstrMessageEvent) -> str:
        """LLM tool handler for refreshing all fortunes."""
        has_perm, msg = PermissionService.require_super_user(event)
        if not has_perm:
            return msg

        config = get_config()
        if not config:
            return self._message("config_not_loaded")

        try:
            repo = get_fortune_repo()
            service = FortuneService(repository=repo)
            refreshed_count = await service.pregenerate_active_users()
            return self._message("fortune_refresh_all_done", count=refreshed_count)
        except Exception as e:
            return self._message("fortune_refresh_all_failed", error=e)

    async def pregenerate_active_fortune_images(self, days: int = 3) -> int:
        """Pregenerate and cache rendered fortune cards for active users."""
        config = get_config()
        if not config or not config.fortune.enabled or not config.fortune.auto_refresh:
            return 0

        repo = get_fortune_repo()
        service = FortuneService(repository=repo)
        access_repo = get_access_control_repo()
        access_service = AccessControlService(access_repo)

        async def can_pregenerate(request: FortuneGenerationRequest) -> bool:
            return access_service.check_access("fortune", request.session_id)

        records = await service.pregenerate_active_user_records(
            days=days,
            include_existing=True,
            access_filter=can_pregenerate,
        )

        cached_count = 0
        for record in records:
            try:
                if await service.get_cached_image(record.user_id, record.date_str):
                    continue
                image_bytes = await self._render_fortune_image(record, service)
                if image_bytes:
                    cached_count += 1
            except Exception as exc:
                logger.warning(
                    "[fortune] Failed to pregenerate cache for %s: %s",
                    record.user_id,
                    exc,
                )
        return cached_count

    # ==================== Helper Methods ====================

    async def _check_access(self, event: AstrMessageEvent, config) -> tuple[bool, str]:
        """Check access using the complete conversation SID."""
        allowed = AccessControlService(get_access_control_repo()).check_access(
            "fortune", get_event_session_identity(event).session_id
        )
        return allowed, "" if allowed else self._message("access_denied")

    def _build_fortune_request(
        self, event: AstrMessageEvent
    ) -> FortuneGenerationRequest:
        """Build a framework-free fortune generation request from an AstrBot event."""
        user_id = str(event.get_sender_id())
        username = user_id
        message_obj = getattr(event, "message_obj", None)
        sender = getattr(message_obj, "sender", None)
        for attr in ("nickname", "name", "user_name"):
            value = getattr(sender, attr, None)
            if value:
                username = str(value)
                break
        group_id = event.get_group_id()
        return FortuneGenerationRequest.for_today(
            user_id=user_id,
            username=username,
            group_id=str(group_id) if group_id else None,
            session_id=get_event_session_identity(event).session_id,
        )

    def _format_fortune(self, result: FortuneRecord) -> str:
        """Format fortune result for message sending."""
        return (
            f"🔮 {result.date_str} 运势\n"
            f"📊 {result.title}\n"
            f"⭐ {'★' * result.star_count}{'☆' * (result.max_stars - result.star_count)}\n"
            f"💬 {result.description}"
        )

    def _plain(self, event: AstrMessageEvent, text: str | None) -> Any | None:
        """Build a plain result only when the configured text is not empty."""
        if not text:
            return None
        return event.plain_result(text)

    async def _render_fortune_image(
        self, record: FortuneRecord, service: FortuneService
    ) -> bytes | None:
        """Render fortune to image, fallback to None when unavailable."""
        cached = await service.get_cached_image(record.user_id, record.date_str)
        if cached:
            return cached

        bg_bytes, img_url = await self._get_fortune_background_image(record.session_id)
        if not bg_bytes:
            return None

        image_base64 = base64.b64encode(bg_bytes).decode("ascii")
        fortune_dict = {
            "username": record.username,
            "date_str": record.date_str,
            "title": record.title,
            "star_count": record.star_count,
            "max_stars": record.max_stars,
            "description": record.description,
            "extra_message": record.extra_message,
            "theme_color": record.theme_color,
        }
        try:
            image_bytes = await self._renderer.render_to_image(
                fortune_dict, image_base64=image_base64
            )
            if image_bytes:
                await service.update_image_cache(record, image_bytes, img_url)
            return image_bytes
        except Exception as exc:
            logger.warning("[fortune] failed to render fortune image: %s", exc)
            return None

    async def _get_fortune_background_image(
        self, session_id: str | None = None
    ) -> tuple[bytes | None, str | None]:
        config = get_config()
        if not config:
            return None, None
        try:
            init_provider_from_config(config)
            provider = get_provider()

            settings = SessionConfigService(config).resolve(session_id)
            tags = [t.strip() for t in settings.fortune_tags.split(",") if t.strip()]
            mode = settings.fortune_content_mode
            if mode == "r18":
                is_r18 = True
            elif mode == "mix":
                is_r18 = random.random() > 0.5
            else:
                is_r18 = False

            request = SetuRequest.from_user_input(
                count=1,
                tags=tags,
                r18=is_r18,
                exclude_ai=config.exclude_ai,
                max_replenish_rounds=config.max_replenish_rounds,
            )
            payload = await provider.fetch_and_download(request)
            if payload.is_empty:
                return None, None

            if payload.raw_bytes:
                return payload.raw_bytes[0], payload.urls[0] if payload.urls else None
            if payload.items and isinstance(payload.items[0], bytes):
                return payload.items[0], payload.urls[0] if payload.urls else None
            if payload.file_paths:
                return payload.file_paths[0].read_bytes(), (
                    payload.urls[0] if payload.urls else None
                )
            return None, None
        except Exception as exc:
            logger.warning("[fortune] failed to fetch background image: %s", exc)
            return None, None

    def _message(self, key: str, **kwargs: Any) -> str:
        config = get_config()
        if config and hasattr(config, "resolve_message"):
            text = config.resolve_message(key, **kwargs)
            if text is not None:
                return text
        return ""


# ==================== LLM Tools Registration ====================


def register_llm_tools() -> None:
    """Register Fortune LLM tools."""
    _handler = FortuneCommandHandler()
    tools = [
        (
            "get_today_fortune",
            _handler._llm_get_fortune,
            [],
            "Send today's fortune image; return a text fortune if image delivery fails.",
        ),
        (
            "refresh_my_fortune",
            _handler._llm_refresh_fortune,
            [],
            "Refresh my today's fortune (admin only).",
        ),
        (
            "refresh_group_fortune",
            _handler._llm_refresh_group_fortune,
            [],
            "Refresh today's fortune for the current group (admin only).",
        ),
        (
            "refresh_all_fortune",
            _handler._llm_refresh_all_fortune,
            [],
            "Refresh today's fortune for all users (super admin only).",
        ),
    ]

    for name, handler, args, desc in tools:
        try:
            llm_tools.add_func(name=name, func_args=args, desc=desc, handler=handler)
            tool = llm_tools.get_func(name)
            if tool:
                tool.handler_module_path = __name__
        except (AttributeError, RuntimeError):
            pass


def unregister_llm_tools() -> None:
    """Unregister Fortune LLM tools."""
    tool_names = [
        "get_today_fortune",
        "refresh_my_fortune",
        "refresh_group_fortune",
        "refresh_all_fortune",
    ]

    for name in tool_names:
        try:
            llm_tools.remove_func(name)
        except (AttributeError, RuntimeError):
            pass
