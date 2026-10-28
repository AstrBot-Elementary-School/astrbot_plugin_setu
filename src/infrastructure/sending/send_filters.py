"""Send filter chain for image sending.

A simpler alternative to the strategy pattern - each filter tries to send
images and returns a result. The chain is configured based on send_mode.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent

from ...shared import get_logger
from ...shared.config import MessagesConfig

logger = get_logger()

SendFilter = Callable[[list[Path], AstrMessageEvent, Any], Awaitable["SendResult"]]


@dataclass
class SendResult:
    """Result of a send filter attempt."""

    success: bool
    images_sent: int = 0
    error: str | None = None


async def direct_send_filter(
    images: list[Path], event: AstrMessageEvent, config: Any
) -> SendResult:
    """Direct send filter - send images directly in message chain.

    Args:
        images: List of image file paths
        event: Message event
        config: Plugin config

    Returns:
        SendResult indicating success or failure
    """
    try:
        for img in images:
            chain = [Comp.Image.fromFileSystem(str(img))]
            result = event.chain_result(chain)
            await event.ctx.send_message(event.unified_msg_origin, result)

        logger.debug("[direct] Sent %d images", len(images))
        return SendResult(success=True, images_sent=len(images))
    except Exception as e:
        logger.warning("[direct] Direct send failed: %s", e)
        return SendResult(success=False, error=str(e))


async def forward_send_filter(
    images: list[Path], event: AstrMessageEvent, config: Any
) -> SendResult:
    """Forward send filter - merge images into a single forward message.

    Args:
        images: List of image file paths
        event: Message event
        config: Plugin config

    Returns:
        SendResult indicating success or failure
    """
    try:
        nodes = []
        for img in images:
            node = Comp.Node(
                uin=event.get_self_id(),
                name="色图",
                content=[Comp.Image.fromFileSystem(str(img))],
            )
            nodes.append(node)

        # 当前 AstrBot 发送合并转发时直接使用 Nodes；Forward 表示已收到的转发消息引用。
        forward_chain = [Comp.Nodes(nodes)]
        result = event.chain_result(forward_chain)
        await event.ctx.send_message(event.unified_msg_origin, result)

        logger.debug("[forward] Sent %d images as forward", len(images))
        return SendResult(success=True, images_sent=len(images))
    except Exception as e:
        logger.warning("[forward] Forward send failed: %s", e)
        return SendResult(success=False, error=str(e))


async def html_card_filter(
    images: list[Path], event: AstrMessageEvent, config: Any
) -> SendResult:
    """HTML card filter - wrap images in HTML card to bypass censorship.

    Args:
        images: List of image file paths
        event: Message event
        config: Plugin config

    Returns:
        SendResult indicating success or failure
    """
    try:
        html_content = _build_html_card(images, config)
        await event.send(html_content)
        logger.debug("[html] Sent %d images as HTML card", len(images))
        return SendResult(success=True, images_sent=len(images))
    except Exception as e:
        logger.warning("[html] HTML card send failed: %s", e)
        return SendResult(success=False, error=str(e))


def _build_html_card(images: list[Path], config: Any) -> str:
    """Build HTML card with images.

    Args:
        images: List of image file paths
        config: Plugin config

    Returns:
        HTML content as string
    """
    opts = config.html_card if config else None
    padding = opts.card_padding if opts else 10

    img_tags = []
    for img in images:
        uri = img.resolve().as_uri()
        img_tags.append(
            f'<img src="{uri}" style="max-width:100%;padding:{padding}px;" />'
        )

    gap_img = '<img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxIiBoZWlnaHQ9IjEwMCIvPg==" style="height:{gap}px;" />'

    content = gap_img.join(img_tags)
    return f'<!DOCTYPE html><html><body style="text-align:center;margin:0;padding:0;">{content}</body></html>'


async def send_with_filter_chain(
    images: list[Path],
    event: AstrMessageEvent,
    config: Any,
) -> str:
    """Send images using filter chain based on config.

    Args:
        images: List of image file paths
        event: Message event
        config: Plugin config

    Returns:
        Result message string
    """
    send_mode = config.delivery.send_mode
    if send_mode:
        send_mode_str = (
            send_mode.value if hasattr(send_mode, "value") else str(send_mode)
        )
    else:
        send_mode_str = "auto"

    # Build filter chain based on send mode
    if send_mode_str == "forward":
        chain = [forward_send_filter, direct_send_filter, html_card_filter]
    elif send_mode_str == "image":
        chain = [direct_send_filter, html_card_filter]
    else:  # auto or unknown
        chain = [direct_send_filter, html_card_filter]

    # Try filters in order
    for filter_func in chain:
        result = await filter_func(images, event, config)
        if result.success:
            return ""

    # All filters failed
    return MessagesConfig.resolve_message("send_failed") or "图片发送失败"


__all__ = [
    "SendResult",
    "SendFilter",
    "direct_send_filter",
    "forward_send_filter",
    "html_card_filter",
    "send_with_filter_chain",
]
