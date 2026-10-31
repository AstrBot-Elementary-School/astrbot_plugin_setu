"""Platform capability helpers for sender strategies."""

from __future__ import annotations

ONEBOT_LIKE_PLATFORM_MARKERS: tuple[str, ...] = (
    "aiocqhttp",
    "onebot11",
    "go-cqhttp",
    "napcat",
    "llonebot",
)


def is_onebot_like_platform(platform_name: str | None) -> bool:
    """判断平台是否属于 OneBot/NapCat 这一类适配器链路。"""
    if not platform_name:
        return False
    normalized = platform_name.lower()
    return any(marker in normalized for marker in ONEBOT_LIKE_PLATFORM_MARKERS)


def supports_forward_messages(
    platform_name: str | None, *, has_call_action: bool = False
) -> bool:
    """判断当前平台是否可尝试 OneBot 合并转发。"""
    if platform_name:
        return is_onebot_like_platform(platform_name)
    return has_call_action
