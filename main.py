"""AstrBot Setu Plugin - Main entry point.

Commands are defined directly on the Star subclass so AstrBot's decorator-based
registration discovers them. Business logic is delegated to handler helpers.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.core import AstrBotConfig
from astrbot.core.star.filter.command import GreedyStr

from .src.domain.setu.triggers import TriggerMatch, match_trigger
from .src.infrastructure.astrbot import get_config, init_config, set_plugin_context
from .src.infrastructure.astrbot.commands.setu import (
    SetuCommandHandler,
)
from .src.infrastructure.astrbot.commands.setu import (
    register_llm_tools as register_setu_llm_tools,
)
from .src.infrastructure.astrbot.commands.setu import (
    unregister_llm_tools as unregister_setu_llm_tools,
)
from .src.infrastructure.persistence import init_access_control_repo, init_fortune_repo
from .src.infrastructure.providers import init_provider_from_config

if TYPE_CHECKING:
    from .src.infrastructure.astrbot.commands.fortune import FortuneCommandHandler

from .src.infrastructure.config import heal_astrbot_plugin_config
from .src.infrastructure.sending import (
    init_revoke_scheduler,
    stop_revoke_scheduler,
)
from .src.shared.send_cache import clear_send_cache, init_send_cache

# Module-level handler singletons
_setu_handler: SetuCommandHandler | None = None
_fortune_handler: FortuneCommandHandler | None = None

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
        in {
            "色图",
            "setu",
            "随机本子",
            "本子",
            "doujinshi",
            "刷新运势",
            "刷新全局运势",
            "运势偏好",
        }
    ):
        return None
    return match_trigger(
        str(event.message_str or "").strip(), config.setu_general.trigger_templates
    )


class NaturalLanguageFilter(filter.CustomFilter):
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        return _match_natural_trigger(event) is not None


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

    async def initialize(self) -> None:
        global _setu_handler, _fortune_handler
        from .src.infrastructure.persistence.database import init_database
        from .src.shared.cache import init_cache

        schema = json.loads(Path(__file__).with_name("_conf_schema.json").read_text())
        cleaned, changes = heal_astrbot_plugin_config(dict(self._plugin_config), schema)
        if changes:
            self._plugin_config.clear()
            self._plugin_config.update(cleaned)
            self._plugin_config.save_config()
        cfg = init_config(cleaned)
        set_plugin_context(self.context)
        data_dir = Path(StarTools.get_data_dir(self.name))
        try:
            init_cache(data_dir / "cache")
            await init_database(data_dir)
            await init_send_cache(data_dir, enabled=cfg.cache.setu)
            init_provider_from_config(cfg)
            await init_access_control_repo(cfg.safety)
            scheduler = await init_revoke_scheduler(data_dir, self.context)
            _setu_handler = SetuCommandHandler(
                data_dir=data_dir,
                plugin_context=self.context,
                revoke_scheduler=scheduler,
            )
            if cfg.fortune.enabled:
                from .src.infrastructure.astrbot.commands.fortune import (
                    FortuneCommandHandler,
                )
                from .src.infrastructure.astrbot.commands.fortune import (
                    register_llm_tools as register_fortune_llm_tools,
                )

                await init_fortune_repo(data_dir)
                _fortune_handler = FortuneCommandHandler()
            if cfg.setu_general.llm_tools_enabled:
                register_setu_llm_tools(_setu_handler)
                if _fortune_handler is not None:
                    register_fortune_llm_tools(_fortune_handler)
            self._apply_registration_switches(cfg)
        except BaseException:
            await self.terminate()
            raise
        logger.info("SetuPlugin initialized")

    def _apply_registration_switches(self, cfg) -> None:
        from astrbot.core.star import star_map
        from astrbot.core.star.star_handler import star_handlers_registry

        for handler in list(
            star_handlers_registry.get_handlers_by_module_name(__name__)
        ):
            enabled = (
                cfg.setu_general.natural_language_enabled
                if handler.handler_name == "regex_command"
                else cfg.setu_general.commands_enabled
            )
            if not cfg.fortune.enabled and (
                handler.handler_name.startswith("fortune_")
                or handler.handler_name.startswith("preference")
            ):
                enabled = False
            if not enabled:
                star_handlers_registry.remove(handler)
        star_map[__name__].star_handler_full_names = [
            h.handler_full_name
            for h in star_handlers_registry.get_handlers_by_module_name(__name__)
        ]

    async def terminate(self) -> None:
        global _setu_handler, _fortune_handler
        from .src.infrastructure.astrbot.config import clear_config
        from .src.infrastructure.persistence import clear_fortune_repo, clear_repo
        from .src.infrastructure.persistence.database import close_database
        from .src.infrastructure.providers import clear_provider
        from .src.shared.cache import clear_cache

        try:
            unregister_setu_llm_tools()
            if _fortune_handler is not None:
                from .src.infrastructure.astrbot.commands.fortune import (
                    unregister_llm_tools,
                )

                unregister_llm_tools()
            await stop_revoke_scheduler()
        finally:
            await close_database()
            clear_send_cache()
            clear_cache()
            clear_provider()
            clear_repo()
            clear_fortune_repo()
            clear_config()
            _setu_handler = None
            _fortune_handler = None

    # ==================== Setu Commands ====================

    @filter.custom_filter(NaturalLanguageFilter)
    async def regex_command(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        """集中处理已匹配的自然语句。"""
        async for result in _route_regex_command(
            event, _setu_handler, _fortune_handler
        ):
            yield result

    @filter.command("色图", alias={"setu"})
    async def setu_command(
        self, event: AstrMessageEvent, count: str = "1", *, tags: GreedyStr
    ) -> AsyncGenerator[Any, None]:
        """/色图 [count] [tags...]"""
        if _setu_handler is None:
            yield event.plain_result("插件未初始化")
            return
        async for result in _setu_handler.setu_command(event, count, tags=tags):
            yield result

    @filter.command("随机本子", alias={"本子", "doujinshi"})
    async def random_doujinshi_command(
        self, event: AstrMessageEvent, *, tags: GreedyStr
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

    @filter.command("刷新运势")
    async def fortune_refresh_command(self, event: AstrMessageEvent):
        async for result in _fortune_handler.refresh_fortune_command(event):
            yield result

    @filter.command("刷新全局运势")
    async def fortune_refresh_all_command(self, event: AstrMessageEvent):
        async for result in _fortune_handler.refresh_all_fortune_command(event):
            yield result

    @filter.command_group("运势偏好")
    async def preference(self, event: AstrMessageEvent):
        """查看或修改个人运势主题与搜索标签。"""

    async def _preference_result(self, event, field=None, value=None):
        try:
            yield event.plain_result(
                await _fortune_handler.preference(event, field, value)
            )
        except Exception as exc:
            yield event.plain_result(f"偏好设置失败：{exc}")

    @preference.command("查看")
    async def preference_show(self, event: AstrMessageEvent):
        async for result in self._preference_result(event):
            yield result

    @preference.command("主题")
    async def preference_theme(self, event: AstrMessageEvent, theme: str):
        async for result in self._preference_result(event, "theme", theme):
            yield result

    @preference.command("标签")
    async def preference_tags(self, event: AstrMessageEvent, *, tags: GreedyStr):
        async for result in self._preference_result(
            event, "tags", json.dumps(tags.split(), ensure_ascii=False)
        ):
            yield result

    @preference.command("重置主题")
    async def preference_reset_theme(self, event: AstrMessageEvent):
        async for result in self._preference_result(event, "theme", None):
            yield result

    @preference.command("重置标签")
    async def preference_reset_tags(self, event: AstrMessageEvent):
        async for result in self._preference_result(event, "tags", None):
            yield result
