"""让直接发送的用户回复沿用 AstrBot 当前会话的 @ 设置。"""

from __future__ import annotations

from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent

_MENTION_SENT = "astrbot_plugin_setu.reply_mention_sent"


def needs_reply_mention(context: Any, event: AstrMessageEvent) -> bool:
    """仅为尚未提醒的群聊请求读取当前会话设置。"""
    return bool(
        event.get_group_id()
        and not event.get_extra(_MENTION_SENT, False)
        and context.get_config(umo=event.unified_msg_origin)["platform_settings"][
            "reply_with_mention"
        ]
    )


def with_reply_mention(
    context: Any, event: AstrMessageEvent, chain: list[Any]
) -> list[Any]:
    """保留原消息链，按需在普通回复前添加请求者 @。"""
    if not needs_reply_mention(context, event) or any(
        isinstance(comp, Comp.At) and str(comp.qq) == str(event.get_sender_id())
        for comp in chain
    ):
        return chain
    return [
        Comp.At(qq=event.get_sender_id(), name=event.get_sender_name()),
        Comp.Plain("\n"),
        *chain,
    ]


def mark_reply_mention(event: AstrMessageEvent, chain: list[Any]) -> None:
    """记录已接收或确认超时的提醒，供分批发送和降级复用。"""
    if any(
        isinstance(comp, Comp.At) and str(comp.qq) == str(event.get_sender_id())
        for comp in chain
    ):
        event.set_extra(_MENTION_SENT, True)
