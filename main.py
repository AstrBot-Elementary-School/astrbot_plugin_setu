"""AstrBot Setu Plugin - Main entry point.

Commands are defined directly on the Star subclass so AstrBot's decorator-based
registration discovers them. Business logic is delegated to handler helpers.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import re
from collections.abc import AsyncGenerator
from contextlib import suppress
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.core import AstrBotConfig

from .src.domain.setu.triggers import TriggerMatch, match_trigger
from .src.infrastructure import (
    init_access_control_repo,
    init_fortune_repo,
    init_provider_from_config,
)
from .src.infrastructure.astrbot import get_config, init_config, set_plugin_context
from .src.infrastructure.astrbot.commands import (
    FortuneCommandHandler,
    SetuCommandHandler,
    register_fortune_llm_tools,
    register_setu_llm_tools,
    unregister_fortune_llm_tools,
    unregister_setu_llm_tools,
)
from .src.infrastructure.config import heal_astrbot_plugin_config
from .src.infrastructure.config.legacy_data_migration import migrate_plugin_config
from .src.infrastructure.sending import (
    init_revoke_scheduler,
    stop_revoke_scheduler,
)
from .src.shared.send_cache import clear_send_cache, init_send_cache

# Module-level handler singletons
_setu_handler: SetuCommandHandler | None = None
_fortune_handler: FortuneCommandHandler | None = None

FORTUNE_REFRESH_ARG_ALIASES = {
    "": "self",
    "我": "self",
    "自己": "self",
    "我的": "self",
    "self": "self",
    "me": "self",
    "本群": "group",
    "群": "group",
    "group": "group",
    "全局": "all",
    "全部": "all",
    "all": "all",
    "global": "all",
}
_LEADING_COMMAND_PREFIX_PATTERN = re.compile(r"^[^\w\u4e00-\u9fff]+")


def _get_invoked_command(event: AstrMessageEvent) -> str:
    raw_message = getattr(event, "message_str", None)
    if not raw_message and hasattr(event, "get_message_str"):
        raw_message = event.get_message_str()
    text = str(raw_message or "").strip()
    if not text:
        return ""
    first_token = text.split(maxsplit=1)[0]
    return _LEADING_COMMAND_PREFIX_PATTERN.sub("", first_token).strip()


def _is_fortune_command_invocation(event: AstrMessageEvent) -> bool:
    """Return True when the message is already handled by fortune command routing."""
    if not getattr(event, "is_at_or_wake_command", False):
        return False
    return _get_invoked_command(event) in {"今日运势", "jrys"}


async def _route_regex_command(
    event: AstrMessageEvent,
    setu_handler: SetuCommandHandler | None,
    fortune_handler: FortuneCommandHandler | None,
) -> AsyncGenerator[Any, None]:
    """把首条匹配短语分发给业务处理器。"""
    matched = _match_natural_trigger(event)
    if matched is None:
        return
    if matched.kind == "setu" and setu_handler is not None:
        async for result in setu_handler.setu_command(
            event, matched.count, tags=matched.tags, natural=True
        ):
            yield result
    elif matched.kind == "doujinshi" and setu_handler is not None:
        async for result in setu_handler.random_doujinshi_command(
            event, tags=matched.tags
        ):
            yield result
    elif matched.kind == "fortune" and fortune_handler is not None:
        async for result in fortune_handler.fortune_command(event):
            yield result


def _match_natural_trigger(event: AstrMessageEvent) -> TriggerMatch | None:
    config = get_config()
    if config is None or not config.setu_general.natural_language_enabled:
        return None
    # AstrBot may invoke both the command and natural-language handlers for one message.
    if _is_fortune_command_invocation(event) or (
        getattr(event, "is_at_or_wake_command", False)
        and _get_invoked_command(event)
        in {"setu", "随机本子", "本子", "doujinshi", "运势刷新"}
    ):
        return None
    return match_trigger(
        str(event.message_str or "").strip(), config.setu_general.trigger_templates
    )


class NaturalLanguageFilter(filter.CustomFilter):
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        return _match_natural_trigger(event) is not None


def _fortune_auto_refresh_enabled(config: Any) -> bool:
    fortune = getattr(config, "fortune", None)
    return (
        getattr(fortune, "enabled", False) is True
        and getattr(fortune, "auto_refresh", False) is True
    )


def _seconds_until_next_midnight() -> float:
    now = datetime.datetime.now()
    tomorrow = now.date() + datetime.timedelta(days=1)
    next_midnight = datetime.datetime.combine(tomorrow, datetime.time.min)
    return max(1.0, (next_midnight - now).total_seconds())


def _load_conf_schema() -> dict[str, Any]:
    """Load plugin config schema for runtime config healing."""
    schema_path = Path(__file__).with_name("_conf_schema.json")
    try:
        return json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load Setu config schema: %s", exc)
        return {}


def _resolve_fortune_refresh_target(event: AstrMessageEvent, args: str) -> str:
    target = FORTUNE_REFRESH_ARG_ALIASES.get((args or "").strip().lower())
    if target:
        return target
    raise ValueError("用法：/运势刷新 [我|本群|全局]")


class SetuPlugin(Star):
    """Main plugin class with command handlers on the Star subclass.

    AstrBot only discovers @filter.command/@filter.regex handlers whose
    __module__ matches the plugin's main module path. Defining handlers
    here ensures they are found and bound to the Star instance.
    """

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context, config)
        self.context = context
        self._plugin_config = config
        self._fortune_pregenerate_task: asyncio.Task[None] | None = None

    async def initialize(self) -> None:
        global _setu_handler, _fortune_handler

        data_dir = Path(StarTools.get_data_dir(self.name))
        migrate_plugin_config(data_dir, self._plugin_config)
        raw_config = self._runtime_plugin_config()
        raw_config = self._heal_runtime_plugin_config(raw_config)
        cfg = init_config(raw_config)
        set_plugin_context(self.context)

        init_provider_from_config(cfg)

        await init_access_control_repo(cfg.safety)
        if cfg.fortune.enabled:
            await init_fortune_repo(data_dir)
        await init_send_cache(
            data_dir,
            enabled=cfg.cache_enabled,
            ttl_hours=cfg.cache_ttl_hours,
            max_items=cfg.cache_max_items,
            cleanup_on_start=cfg.cache_cleanup_on_start,
        )
        revoke_scheduler = await init_revoke_scheduler(data_dir, self.context)

        _setu_handler = SetuCommandHandler(
            data_dir=Path(data_dir),
            plugin_context=self.context,
            revoke_scheduler=revoke_scheduler,
        )
        _fortune_handler = FortuneCommandHandler()
        if _fortune_auto_refresh_enabled(cfg):
            self._fortune_pregenerate_task = asyncio.create_task(
                self._fortune_pregenerate_loop(), name="setu_fortune_pregenerate"
            )

        try:
            if cfg.setu_general.llm_tools_enabled:
                register_setu_llm_tools()
                if cfg.fortune.enabled:
                    register_fortune_llm_tools()
        except Exception as e:
            logger.warning("Failed to register LLM tools: %s", e)

        logger.info("SetuPlugin initialized successfully")

    async def terminate(self) -> None:
        global _setu_handler, _fortune_handler

        from .src.infrastructure import (
            clear_fortune_repo,
            clear_provider,
            clear_repo,
        )

        if self._fortune_pregenerate_task is not None:
            self._fortune_pregenerate_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._fortune_pregenerate_task
            self._fortune_pregenerate_task = None

        try:
            unregister_setu_llm_tools()
            unregister_fortune_llm_tools()
        except Exception:
            pass

        clear_provider()
        clear_repo()
        clear_fortune_repo()
        await stop_revoke_scheduler()
        clear_send_cache()

        _setu_handler = None
        _fortune_handler = None

        logger.info("SetuPlugin terminated")

    async def _fortune_pregenerate_loop(self) -> None:
        """Cache fortune card images for recently active users after day rollover."""
        while True:
            await asyncio.sleep(_seconds_until_next_midnight())
            await self._pregenerate_active_fortune_images()

    async def _pregenerate_active_fortune_images(self) -> None:
        if _fortune_handler is None:
            return
        try:
            cached_count = await _fortune_handler.pregenerate_active_fortune_images()
            if cached_count:
                logger.info(
                    "[fortune] Pregenerated %d rendered fortune card caches",
                    cached_count,
                )
            else:
                logger.debug("[fortune] No fortune card caches pregenerated")
        except Exception as exc:
            logger.warning(
                "[fortune] Failed to pregenerate fortune card caches: %s", exc
            )

    def _runtime_plugin_config(self) -> dict[str, Any]:
        """Return the plugin-scoped config dict passed in by AstrBot."""
        if isinstance(self._plugin_config, dict):
            return dict(self._plugin_config)
        items = getattr(self._plugin_config, "items", None)
        if callable(items):
            return dict(items())
        return dict(self._plugin_config)

    def _heal_runtime_plugin_config(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        """Heal legacy or invalid config values before runtime initialization."""
        schema = _load_conf_schema()
        healed_config, changes = heal_astrbot_plugin_config(raw_config, schema)
        if not changes:
            return healed_config
        logger.info("SetuPlugin healed config: %s", "; ".join(changes))
        if not self._persist_runtime_plugin_config(healed_config):
            logger.warning("SetuPlugin config healed for runtime but could not persist")
        return healed_config

    def _persist_runtime_plugin_config(self, healed_config: dict[str, Any]) -> bool:
        """Best-effort write-back for AstrBotConfig-like mapping objects."""
        target = self._plugin_config
        try:
            clear = getattr(target, "clear", None)
            update = getattr(target, "update", None)
            if callable(clear) and callable(update):
                clear()
                update(healed_config)
                target.save_config()
                return True

            pop = getattr(target, "pop", None)
            keys = getattr(target, "keys", None)
            if callable(pop) and callable(keys):
                for key in list(keys()):
                    if key not in healed_config:
                        pop(key, None)

            for key, value in healed_config.items():
                target[key] = value
            target.save_config()
            return True
        except Exception as exc:
            logger.debug("failed to persist healed Setu config: %s", exc)
            return False

    # ==================== Setu Commands ====================

    @filter.custom_filter(NaturalLanguageFilter)
    async def regex_command(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        """集中处理已匹配的自然语句。"""
        async for result in _route_regex_command(
            event, _setu_handler, _fortune_handler
        ):
            yield result

    @filter.command("setu")
    async def setu_command(
        self, event: AstrMessageEvent, count: str = "1", *, tags: str = ""
    ) -> AsyncGenerator[Any, None]:
        """/setu [count] [tags...]"""
        if _setu_handler is None:
            yield event.plain_result("插件未初始化")
            return
        async for result in _setu_handler.setu_command(event, count, tags=tags):
            yield result

    @filter.command("随机本子", alias={"本子", "doujinshi"})
    async def random_doujinshi_command(
        self, event: AstrMessageEvent, *, tags: str = ""
    ) -> AsyncGenerator[Any, None]:
        """获取可选标签的随机本子 PDF。"""
        if _setu_handler is None:
            yield event.plain_result("插件未初始化")
            return
        async for result in _setu_handler.random_doujinshi_command(event, tags=tags):
            yield result

    # ==================== Fortune Commands ====================

    @filter.command("今日运势", alias={"jrys"})
    async def fortune_command(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[Any, None]:
        """今日运势 / jrys"""
        if _fortune_handler is None:
            yield event.plain_result("插件未初始化")
            return
        async for result in _fortune_handler.fortune_command(event):
            yield result

    @filter.command("运势刷新")
    async def fortune_refresh_command(
        self, event: AstrMessageEvent, args: str = ""
    ) -> AsyncGenerator[Any, None]:
        """运势刷新 [我|本群|全局]"""
        if _fortune_handler is None:
            yield event.plain_result("插件未初始化")
            return

        try:
            target = _resolve_fortune_refresh_target(event, args)
        except ValueError as exc:
            yield event.plain_result(str(exc))
            return

        handler_map = {
            "self": _fortune_handler.refresh_fortune_command,
            "group": _fortune_handler.refresh_group_fortune_command,
            "all": _fortune_handler.refresh_all_fortune_command,
        }
        async for result in handler_map[target](event):
            yield result
