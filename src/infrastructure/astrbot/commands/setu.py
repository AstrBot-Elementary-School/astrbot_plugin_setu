"""Setu command handler - all Setu-related commands."""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from astrbot.api.event import AstrMessageEvent
from astrbot.core.provider.register import llm_tools

from ....application.session_config import SessionConfigService
from ....application.setu.get_images import GetSetuImagesUseCase
from ....application.setu.tag_resolution import (
    resolve_image_request_tags,
    resolve_user_tags,
)
from ....domain.access_control.service import AccessControlService
from ....domain.setu import SetuRequest
from ....shared import get_logger
from ....shared.cache import get_cache
from ....shared.config.messages import MessagesConfig
from ...doujinshi import DoujinshiService
from ...persistence import get_access_control_repo
from ...persistence.database import get_database
from ...providers import get_provider
from ...sending import (
    DirectSendStrategy,
    build_doujinshi_file_chain,
    get_revoke_scheduler,
)
from ...sending.platform_capabilities import is_onebot_like_platform
from ...sending.revoke_scheduler import RecoverableRevokeScheduler
from ..config import get_config, get_plugin_context
from ..session_identity import get_event_session_identity

logger = get_logger()


def _platform_name(event: AstrMessageEvent) -> str | None:
    """返回事件平台名称。"""
    name = getattr(getattr(event, "platform", None), "name", None)
    if isinstance(name, str) and name:
        return name
    getter = getattr(event, "get_platform_name", None)
    if callable(getter):
        value = getter()
        if isinstance(value, str) and value:
            return value
    return None


class RateLimiter:
    """Simple rate limiter to prevent concurrent requests from same user."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    async def acquire(self, event: AstrMessageEvent) -> bool:
        key = str(event.get_sender_id())
        if key in self._locks:
            return False
        lock = asyncio.Lock()
        self._locks[key] = lock
        await lock.acquire()
        return True

    async def release(self, event: AstrMessageEvent) -> None:
        self._locks.pop(str(event.get_sender_id())).release()


# Module-level rate limiter singleton
_rate_limiter = RateLimiter()


class SetuCommandHandler:
    """Handles all Setu-related commands.

    Uses singleton pattern for config, provider, and access control repo.
    Commands are auto-registered by AstrBot decorators.
    """

    def __init__(
        self,
        data_dir: Path | str | None = None,
        *,
        plugin_context: object | None = None,
        revoke_scheduler: RecoverableRevokeScheduler | None = None,
    ) -> None:
        from ...sending.docx_service import R18DocxService

        self._docx_service = R18DocxService(data_dir) if data_dir is not None else None
        self._doujinshi_service = (
            DoujinshiService(data_dir) if data_dir is not None else None
        )
        # 生命周期依赖在初始化时注入，避免热重载时读取到另一模块实例的全局单例。
        self._plugin_context = plugin_context
        self._revoke_scheduler = revoke_scheduler

    # ==================== Command Handlers ====================

    async def setu_command(
        self,
        event: AstrMessageEvent,
        count: str = "1",
        *,
        tags: str = "",
        natural: bool = False,
    ) -> AsyncGenerator[Any, None]:
        """Handle /setu command.

        Usage: /setu [count] [tags...]
        Example: /setu 3 girl cute
        """
        if not await _rate_limiter.acquire(event):
            if result := self._plain(event, self._message("rate_limited")):
                yield result
            event.stop_event()
            return

        try:
            async for result in self._handle_setu_command_internal(
                event, count, tags, natural=natural
            ):
                yield result
            event.stop_event()
        finally:
            await _rate_limiter.release(event)

    async def random_doujinshi_command(
        self, event: AstrMessageEvent, *, tags: str = ""
    ) -> AsyncGenerator[Any, None]:
        """按可选标签获取随机本子并发送配置指定的文件格式。"""
        if not await _rate_limiter.acquire(event):
            if result := self._plain(event, self._message("rate_limited")):
                yield result
            event.stop_event()
            return

        try:
            async for result in self._handle_random_doujinshi_internal(event, tags):
                yield result
            event.stop_event()
        finally:
            await _rate_limiter.release(event)

    async def _handle_random_doujinshi_internal(
        self, event: AstrMessageEvent, raw_tags: str
    ) -> AsyncGenerator[Any, None]:
        config = get_config()
        if not config:
            if result := self._plain(event, self._message("config_not_loaded")):
                yield result
            return

        if not config.delivery.doujinshi_enabled:
            yield event.plain_result(
                self._message("feature_disabled", feature="随机本子")
            )
            return

        has_perm, msg = await self._check_access(event, config)
        if not has_perm:
            if result := self._plain(event, msg):
                yield result
            return

        if self._doujinshi_service is None:
            logger.error(
                "Doujinshi service is unavailable before plugin initialization"
            )
            if result := self._plain(event, self._message("doujinshi_failed")):
                yield result
            return

        generated = None
        pending = False
        try:
            tags = resolve_user_tags(raw_tags, getattr(config, "tag_alias", ""))
            generated = await self._doujinshi_service.fetch_random_file(
                tags=tags,
                mode=getattr(config, "doujinshi_send_mode", "pdf"),
                max_page=getattr(config, "doujinshi_max_page", 0),
            )
            platform_name = _platform_name(event)
            chain = build_doujinshi_file_chain(generated)
            scheduler = self._revoke_scheduler
            if scheduler is None:
                scheduler = get_revoke_scheduler()
            plugin_context = self._plugin_context
            if plugin_context is None:
                plugin_context = get_plugin_context()
            revoke_delay = config.auto_revoke_delay
            auto_revoke_requested = (
                config.auto_revoke_doujinshi_enabled
                and is_onebot_like_platform(platform_name)
                and bool(event.get_group_id())
                and revoke_delay > 0
            )
            if auto_revoke_requested:
                if scheduler is None:
                    logger.warning(
                        "[doujinshi] 自动撤回已启用但调度器未初始化，将按普通文件发送"
                    )
                elif plugin_context is None:
                    logger.warning(
                        "[doujinshi] 自动撤回已启用但插件上下文未初始化，"
                        "将按普通文件发送"
                    )
                else:
                    send_result = await DirectSendStrategy(
                        plugin_context
                    ).send_with_status(event, chain, auto_revoke=True)
                    pending = send_result.pending
                    if send_result.accepted:
                        scheduled_count = 0
                        for message_id in send_result.message_ids:
                            if await scheduler.schedule_revoke(
                                event, message_id, revoke_delay
                            ):
                                scheduled_count += 1
                        if not send_result.message_ids:
                            logger.warning(
                                "[doujinshi] 本子文件已发送但未返回 message_id，"
                                "无法登记自动撤回"
                            )
                        elif scheduled_count != len(send_result.message_ids):
                            logger.warning(
                                "[doujinshi] 部分本子文件消息未能登记自动撤回: "
                                "scheduled=%s, total=%s",
                                scheduled_count,
                                len(send_result.message_ids),
                            )
                        else:
                            logger.info(
                                "[doujinshi] 已登记本子文件自动撤回: "
                                "messages=%s, delay=%ss",
                                scheduled_count,
                                revoke_delay,
                            )
                        return
            send_result = await DirectSendStrategy(plugin_context).send_with_status(
                event, chain
            )
            pending = send_result.pending
            if not send_result.accepted:
                raise RuntimeError(send_result.reason)
        except Exception as exc:
            logger.exception("random doujinshi command failed")
            if result := self._plain(
                event, self._message("doujinshi_failed") + f"：{exc}"
            ):
                yield result
        finally:
            if generated is not None and not pending:
                get_cache().release(generated.path, keep=config.cache.doujinshi)

    async def _handle_setu_command_internal(
        self, event: AstrMessageEvent, count: str, tags: str, *, natural: bool = False
    ) -> AsyncGenerator[Any, None]:
        """Internal handler for /setu command."""
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

        max_count = config.max_count or 10
        num = self._parse_count(count)
        extra_tag = ""

        if num == -1 and not natural:
            num = 1
            extra_tag = count

        all_tags = tags
        if extra_tag:
            all_tags = f"{extra_tag} {all_tags}".strip()

        if num < 1 or num > max_count:
            text = self._message("invalid_count", min_count=1, max_count=max_count)
            if result := self._plain(event, text):
                yield result
            return

        parsed_tags, explicit_r18 = resolve_image_request_tags(
            all_tags, config.tag_alias
        )

        effective_mode = await self._get_effective_content_mode(event)
        if explicit_r18 and effective_mode == "sfw":
            yield event.plain_result(self._message("r18_not_allowed"))
            return
        is_r18 = explicit_r18 or self._mode_requires_r18(effective_mode)

        try:
            async for result in self._fetch_and_send_images(
                event, num, parsed_tags, is_r18, config
            ):
                yield result
        except asyncio.TimeoutError:
            logger.warning("setu command timeout (>60s)")
            if result := self._plain(event, self._message("fetch_timeout")):
                yield result
        except Exception as exc:
            logger.exception("色图请求失败")
            if result := self._plain(event, f"获取图片失败：{exc}"):
                yield result

    # ==================== LLM Tool Handlers ====================

    async def _llm_get_setu_handler(
        self, event: AstrMessageEvent, count: int = 1, tags: list[str] | None = None
    ) -> str:
        """LLM tool handler for getting Setu images."""
        config = get_config()
        if not config:
            return self._message("config_not_loaded")

        if not config.setu_general.llm_tools_enabled:
            return self._message("feature_disabled", feature="LLM 工具")
        has_perm, msg = await self._check_access(event, config)
        if not has_perm:
            return msg

        parsed_tags, explicit_r18 = resolve_image_request_tags(
            tags or [], config.tag_alias
        )
        effective_mode = await self._get_effective_content_mode(event)
        if explicit_r18 and effective_mode == "sfw":
            return self._message("r18_not_allowed")
        try:
            provider = get_provider()
            request = SetuRequest.from_user_input(
                count=count,
                tags=parsed_tags,
                r18=explicit_r18 or self._mode_requires_r18(effective_mode),
                exclude_ai=config.exclude_ai,
                max_replenish_rounds=config.max_replenish_rounds,
            )
            payload = await provider.fetch_and_download(
                request,
                on_images=lambda images: self._record_history(
                    event, images, parsed_tags
                ),
            )
            from ...sending import ImageSender

            sender = ImageSender(config, logger, docx_service=self._docx_service)
            accepted = False
            async for result in sender.send_images(payload, event):
                if isinstance(result, dict):
                    accepted = accepted or bool(result.get("send_success"))
                else:
                    await (self._plugin_context or get_plugin_context()).send_message(
                        event.unified_msg_origin, result
                    )
            if not accepted:
                return self._message("send_failed")
            return "ok"
        except Exception as exc:
            logger.exception("色图请求失败")
            return self._message("fetch_failed") + f"：{exc}"

    # ==================== Helper Methods ====================

    async def _check_access(self, event: AstrMessageEvent, config) -> tuple[bool, str]:
        """Check access using the complete conversation SID."""
        allowed = AccessControlService(get_access_control_repo()).check_access(
            "setu", get_event_session_identity(event).session_id
        )
        return allowed, "" if allowed else self._message("access_denied")

    async def _fetch_and_send_images(
        self, event: AstrMessageEvent, num: int, tags: list[str], is_r18: bool, config
    ) -> AsyncGenerator[Any, None]:
        """Fetch images and send to user."""
        provider = get_provider()
        use_case = GetSetuImagesUseCase(
            provider, lambda images: self._record_history(event, images, tags)
        )

        try:
            result = await use_case.execute(num, tags, is_r18)
        except asyncio.TimeoutError:
            logger.warning("image fetch timeout (>60s)")
            if result := self._plain(event, self._message("fetch_timeout")):
                yield result
            return

        payload = result.payload
        if payload.is_empty:
            tags_info = f"标签: {', '.join(tags)}" if tags else ""
            text = self._message("no_result", tags_info=tags_info)
            if result := self._plain(event, text):
                yield result
            return

        from ...sending import ImageSender

        sender = ImageSender(config, logger, docx_service=self._docx_service)
        async for send_result in sender.send_images(payload, event):
            yield send_result

    async def _record_history(self, event, images, tags):
        await get_database().add_history(
            get_event_session_identity(event).session_id,
            str(event.get_sender_id()),
            images,
            tags,
        )

    async def _get_effective_content_mode(self, event: AstrMessageEvent) -> str:
        """Get effective content mode for session."""
        config = get_config()
        if config is None:
            return "sfw"
        identity = get_event_session_identity(event)
        return SessionConfigService(config).resolve(identity.session_id).content_mode

    @staticmethod
    def _mode_requires_r18(mode: str) -> bool:
        """Resolve content mode to the provider R18 flag."""
        if mode == "r18":
            return True
        if mode == "mix":
            return random.random() > 0.5
        return False

    def _parse_count(self, count_str: str) -> int:
        """Parse count from string, handling Chinese numbers."""
        if not count_str:
            return 1

        try:
            return int(count_str)
        except ValueError:
            pass

        chinese_nums = {
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }
        if count_str in chinese_nums:
            return chinese_nums[count_str]

        if count_str.startswith("十"):
            if len(count_str) == 1:
                return 10
            try:
                return 10 + int(count_str[1])
            except ValueError:
                return 10

        return -1

    def _plain(self, event: AstrMessageEvent, text: str | None) -> Any | None:
        """Build a plain result only when the configured text is not empty."""
        if not text:
            return None
        return event.plain_result(text)

    def _message(self, key: str, **kwargs: Any) -> str:
        return MessagesConfig.resolve_message(key, **kwargs) or ""


# ==================== LLM Tools Registration ====================


def register_llm_tools(handler: SetuCommandHandler) -> None:
    """Register Setu LLM tools."""
    config = get_config()
    if config is None or not config.setu_general.llm_tools_enabled:
        return
    tools = [
        (
            "get_setu_image",
            handler._llm_get_setu_handler,
            [
                {
                    "name": "count",
                    "type": "integer",
                    "description": "Number of images.",
                },
                {"name": "tags", "type": "array", "items": {"type": "string"}},
            ],
            "Fetch random anime images.",
        ),
    ]

    for name, method, args, desc in tools:
        llm_tools.add_func(name=name, func_args=args, desc=desc, handler=method)
        llm_tools.get_func(name).handler_module_path = __name__


def unregister_llm_tools() -> None:
    if llm_tools.get_func("get_setu_image") is not None:
        llm_tools.remove_func("get_setu_image")
