"""Setu command handler - all Setu-related commands."""

from __future__ import annotations

import asyncio
import random
import re
import time
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
from ....domain.access_control import AccessPolicy
from ....domain.access_control.service import AccessControlService
from ....domain.setu import SetuRequest
from ....shared import get_logger
from ... import get_access_control_repo, get_provider
from ...doujinshi import DoujinshiService
from ...persistence import get_session_config_repo
from ...providers import init_provider_from_config
from ...sending import (
    DirectSendStrategy,
    build_doujinshi_file_chain,
    get_revoke_scheduler,
)
from ...sending.platform_capabilities import is_onebot_like_platform
from ...sending.revoke_scheduler import RecoverableRevokeScheduler
from ..config import get_config, get_plugin_context
from ..feature_switches import feature_enabled, require_feature
from ..session_identity import get_event_session_identity

logger = get_logger()

# Regex pattern directly in decorator (not in constants)
SETU_REGEX_PATTERN = (
    r"^/?(来\s*(.*?)(份|个|张|点))(.*?)(?:福利|色|瑟|涩|塞)?图"
    r"(?P<flags>(?:\s+[rR]18)*)\s*$"
)


def _platform_name(event: AstrMessageEvent) -> str | None:
    """返回事件平台名称，并兼容测试替身的最小接口。"""
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

    MAX_LOCKS = 1000
    LOCK_TTL = 120  # Auto-release locks after 120s

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._lock_times: dict[str, float] = {}

    async def acquire(self, event: AstrMessageEvent) -> bool:
        """Acquire lock for event. Returns True if acquired, False if already processing."""
        key = f"user:{event.get_sender_id()}"
        lock = self._locks.setdefault(key, asyncio.Lock())

        # Auto-release stale locks (safety net for leaked locks)
        if lock.locked():
            acquire_time = self._lock_times.get(key, 0)
            if time.monotonic() - acquire_time > self.LOCK_TTL:
                try:
                    lock.release()
                except RuntimeError:
                    pass

        if lock.locked():
            return False
        await lock.acquire()
        self._lock_times[key] = time.monotonic()
        return True

    async def release(self, event: AstrMessageEvent) -> None:
        """Release lock for event and evict stale entries."""
        key = f"user:{event.get_sender_id()}"
        if key in self._locks:
            self._locks[key].release()
            self._lock_times.pop(key, None)
        if len(self._locks) > self.MAX_LOCKS:
            stale = [k for k, v in self._locks.items() if not v.locked()]
            for k in stale[: len(stale) // 2]:
                del self._locks[k]
                self._lock_times.pop(k, None)


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
        self._doujinshi_service = (
            DoujinshiService(data_dir)
            if data_dir is not None and feature_enabled("doujinshi")
            else None
        )
        # 生命周期依赖在初始化时注入，避免热重载时读取到另一模块实例的全局单例。
        self._plugin_context = plugin_context
        self._revoke_scheduler = revoke_scheduler

    # ==================== Command Handlers ====================

    async def get_random_picture(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[Any, None]:
        """Handle natural language setu requests (regex trigger)."""
        if not await _rate_limiter.acquire(event):
            if result := self._plain(event, self._message("rate_limited")):
                yield result
            return

        try:
            async for result in self._handle_random_picture_internal(event):
                yield result
        finally:
            await _rate_limiter.release(event)

    async def _handle_random_picture_internal(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[Any, None]:
        """Internal handler for regex-triggered setu requests."""
        config = get_config()
        if not config:
            if result := self._plain(event, self._message("config_not_loaded")):
                yield result
            return

        match = re.match(SETU_REGEX_PATTERN, event.message_str.strip())
        if not match:
            return

        has_perm, msg = await self._check_access(event, config)
        if not has_perm:
            if result := self._plain(event, msg):
                yield result
            return

        num_str = match.group(2)
        num = self._parse_count(num_str)
        max_count = config.max_count or 10

        if num < 1 or num > max_count:
            if num == -1:
                text = self._message("invalid_count", min_count=1, max_count=max_count)
            elif num > max_count:
                text = self._message("max_count_exceeded", max_count=max_count)
            else:
                text = self._message(
                    "count_out_of_range", min_count=1, max_count=max_count
                )
            if result := self._plain(event, text):
                yield result
            return

        tag_str = f"{match.group(4)} {match.group('flags')}".strip()
        tags, request_r18 = resolve_image_request_tags(
            tag_str, getattr(config, "tag_alias", "")
        )

        effective_mode = await self._get_effective_content_mode(event)
        is_r18 = request_r18 or self._mode_requires_r18(effective_mode)

        try:
            async for result in self._fetch_and_send_images(
                event, num, tags, is_r18, config
            ):
                yield result
        except asyncio.TimeoutError:
            logger.warning("get_random_picture timeout (>60s)")
            if result := self._plain(event, self._message("fetch_timeout")):
                yield result
        except Exception:
            logger.exception("get_random_picture failed")
            if result := self._plain(event, self._message("fetch_failed")):
                yield result

    async def setu_command(
        self, event: AstrMessageEvent, count: str = "1", *, tags: str = ""
    ) -> AsyncGenerator[Any, None]:
        """Handle /setu command.

        Usage: /setu [count] [tags...]
        Example: /setu 3 girl cute
        """
        if not await _rate_limiter.acquire(event):
            if result := self._plain(event, self._message("rate_limited")):
                yield result
            return

        try:
            async for result in self._handle_setu_command_internal(event, count, tags):
                yield result
        finally:
            await _rate_limiter.release(event)

    @require_feature("doujinshi", "随机本子", "enabled")
    async def random_doujinshi_command(
        self, event: AstrMessageEvent, *, tags: str = ""
    ) -> AsyncGenerator[Any, None]:
        """按可选标签获取随机本子并发送配置指定的文件格式。"""
        if not await _rate_limiter.acquire(event):
            if result := self._plain(event, self._message("rate_limited")):
                yield result
            return

        try:
            async for result in self._handle_random_doujinshi_internal(event, tags):
                yield result
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

        has_perm, msg = await self._check_access(event, config)
        if not has_perm:
            if result := self._plain(event, msg):
                yield result
            return

        if result := self._plain(event, self._message("doujinshi_fetching")):
            yield result

        if self._doujinshi_service is None:
            logger.error(
                "Doujinshi service is unavailable before plugin initialization"
            )
            if result := self._plain(event, self._message("doujinshi_failed")):
                yield result
            return

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
            yield event.chain_result(chain)
        except Exception:
            logger.exception("random doujinshi command failed")
            if result := self._plain(event, self._message("doujinshi_failed")):
                yield result

    async def _handle_setu_command_internal(
        self, event: AstrMessageEvent, count: str, tags: str
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

        if num == -1:
            num = 1
            extra_tag = count

        all_tags = tags
        if extra_tag:
            all_tags = f"{extra_tag} {all_tags}".strip()

        if num > max_count:
            text = self._message("max_count_exceeded", max_count=max_count)
            if result := self._plain(event, text):
                yield result
            return

        parsed_tags, request_r18 = resolve_image_request_tags(
            all_tags, getattr(config, "tag_alias", "")
        )

        effective_mode = await self._get_effective_content_mode(event)
        is_r18 = request_r18 or self._mode_requires_r18(effective_mode)

        try:
            async for result in self._fetch_and_send_images(
                event, num, parsed_tags, is_r18, config
            ):
                yield result
        except asyncio.TimeoutError:
            logger.warning("setu command timeout (>60s)")
            if result := self._plain(event, self._message("fetch_timeout")):
                yield result
        except Exception:
            logger.exception("setu command failed")
            if result := self._plain(event, self._message("fetch_failed")):
                yield result

    # ==================== LLM Tool Handlers ====================

    @require_feature("llm_tools", "LLM 工具", "enabled")
    async def _llm_get_setu_handler(
        self, event: AstrMessageEvent, count: int = 1, tags: list[str] | None = None
    ) -> str:
        """LLM tool handler for getting Setu images."""
        config = get_config()
        if not config:
            return self._message("config_not_loaded")

        has_perm, msg = await self._check_access(event, config)
        if not has_perm:
            return msg

        try:
            init_provider_from_config(config)
            provider = get_provider()
            effective_mode = await self._get_effective_content_mode(event)
            parsed_tags, request_r18 = resolve_image_request_tags(
                tags or [], getattr(config, "tag_alias", "")
            )
            request = SetuRequest.from_user_input(
                count=count,
                tags=parsed_tags,
                r18=request_r18 or self._mode_requires_r18(effective_mode),
                exclude_ai=config.exclude_ai,
                max_replenish_rounds=config.max_replenish_rounds,
            )
            payload = await provider.fetch_and_download(request)
            from ...sending import ImageSender

            sender = ImageSender(config, logger)
            async for _ in sender.send_images(payload, event):
                pass
            return f"Successfully fetched {payload.count} images"
        except Exception:
            return self._message("fetch_failed")

    # ==================== Helper Methods ====================

    async def _check_access(self, event: AstrMessageEvent, config) -> tuple[bool, str]:
        """Check if user/group has access to Setu feature."""
        repo = get_access_control_repo()
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        modes = repo.get_modes()
        policy = AccessPolicy.for_session(
            user_id=user_id,
            group_id=group_id,
            user_mode=modes.get(
                "setu_user_access_control_mode", config.setu_user_access_control_mode
            ),
            group_mode=modes.get(
                "setu_group_access_control_mode", config.setu_group_access_control_mode
            ),
        )
        return await AccessControlService(repo).check_setu_access(policy)

    async def _fetch_and_send_images(
        self, event: AstrMessageEvent, num: int, tags: list[str], is_r18: bool, config
    ) -> AsyncGenerator[Any, None]:
        """Fetch images and send to user."""
        fetching_message = self._message("fetching")
        if fetching_message:
            yield event.plain_result(fetching_message)

        init_provider_from_config(config)
        provider = get_provider()
        use_case = GetSetuImagesUseCase(provider)

        try:
            result = await use_case.execute(num, tags, is_r18)
        except asyncio.TimeoutError:
            logger.warning("image fetch timeout (>60s)")
            if result := self._plain(event, self._message("fetch_timeout")):
                yield result
            return

        payload = result.payload
        if payload is None:
            tags_info = f"标签: {', '.join(tags)}" if tags else ""
            text = self._message("no_result", tags_info=tags_info)
            if result := self._plain(event, text):
                yield result
            return

        from ...sending import ImageSender

        sender = ImageSender(config, logger)
        async for send_result in sender.send_images(payload, event):
            yield send_result

    async def _get_effective_content_mode(self, event: AstrMessageEvent) -> str:
        """Get effective content mode for session."""
        config = get_config()
        global_mode = (config.content_mode if config else None) or "sfw"
        try:
            identity = get_event_session_identity(event)
            service = SessionConfigService(get_session_config_repo())
            value = await service.get_effective_value(
                identity.session_id,
                "setu.content_mode",
                identity.session_type,
                identity.display_name,
            )
            return str(value)
        except Exception as exc:
            logger.debug("Failed to read session content mode: %s", exc)
            return global_mode

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
        """Resolve configured message text."""
        config = get_config()
        if config and hasattr(config, "resolve_message"):
            text = config.resolve_message(key, **kwargs)
            if text is not None:
                return text
        return ""


# ==================== LLM Tools Registration ====================


def register_llm_tools() -> None:
    """Register Setu LLM tools."""
    if not feature_enabled("llm_tools"):
        return
    _handler = SetuCommandHandler()
    tools = [
        (
            "get_setu_image",
            _handler._llm_get_setu_handler,
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

    for name, handler, args, desc in tools:
        try:
            llm_tools.add_func(name=name, func_args=args, desc=desc, handler=handler)
            tool = llm_tools.get_func(name)
            if tool:
                tool.handler_module_path = __name__
        except (AttributeError, RuntimeError):
            pass


def unregister_llm_tools() -> None:
    """Unregister Setu LLM tools."""
    tool_names = [
        "get_setu_image",
    ]

    for name in tool_names:
        try:
            llm_tools.remove_func(name)
        except (AttributeError, RuntimeError):
            pass
