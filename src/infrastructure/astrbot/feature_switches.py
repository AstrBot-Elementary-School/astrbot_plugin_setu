"""Feature gates shared by command and tool entry points."""

from __future__ import annotations

from functools import wraps
from inspect import isasyncgenfunction
from typing import Any

from .config import get_config


def feature_enabled(section: str, field: str = "enabled", config: Any = None) -> bool:
    """Missing switches remain enabled for compatibility with older configs."""
    config = config if config is not None else get_config()
    return bool(getattr(getattr(config, section, None), field, True))


def require_feature(section: str, label: str, field: str = "enabled"):
    """Block disabled entry points before locks, network calls or state changes."""

    def decorate(handler):
        if isasyncgenfunction(handler):

            @wraps(handler)
            async def generator(self, event, *args, **kwargs):
                if not feature_enabled(section, field):
                    config = get_config()
                    text = config.resolve_message("feature_disabled", feature=label)
                    if text:
                        yield event.plain_result(text)
                    return
                async for result in handler(self, event, *args, **kwargs):
                    yield result

            return generator

        @wraps(handler)
        async def coroutine(self, event, *args, **kwargs):
            if not feature_enabled(section, field):
                config = get_config()
                return config.resolve_message("feature_disabled", feature=label) or ""
            return await handler(self, event, *args, **kwargs)

        return coroutine

    return decorate
