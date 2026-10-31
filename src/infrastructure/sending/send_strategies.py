"""Send strategy pattern for image delivery.

Defines the strategy interface and implementations for different send modes:
- Direct send: send images directly in message chain
- Forward send: use merge forward (OneBot v11 feature)
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent

from ...shared import get_logger
from .dto import SendAttemptResult
from .platform_capabilities import is_onebot_like_platform

logger = get_logger()


def extract_message_ids(response: Any) -> tuple[str, ...]:
    """Extract OneBot message ids from common adapter response shapes."""
    ids: list[str] = []

    def collect(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str | int):
            text = str(value).strip()
            if text:
                ids.append(text)
            return
        if isinstance(value, dict):
            for key in ("message_id", "msg_id"):
                if key in value:
                    collect(value[key])
            if "message_ids" in value:
                collect(value["message_ids"])
            data = value.get("data")
            if isinstance(data, dict | list | tuple):
                collect(data)
            return
        if isinstance(value, list | tuple | set):
            for item in value:
                collect(item)

    collect(response)
    unique: list[str] = []
    seen: set[str] = set()
    for item in ids:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return tuple(unique)


def _get_bot_client(event: AstrMessageEvent) -> Any | None:
    return getattr(event, "bot", None) or getattr(event, "_bot", None)


def _onebot_target(event: AstrMessageEvent) -> tuple[str, int] | None:
    group_id = event.get_group_id()
    if group_id:
        text = str(group_id)
        if text.isdigit():
            return "group", int(text)
        logger.debug("[send] skip OneBot raw send: invalid group_id=%s", group_id)
        return None

    sender_id = event.get_sender_id()
    if sender_id:
        text = str(sender_id)
        if text.isdigit():
            return "private", int(text)
        logger.debug("[send] skip OneBot raw send: invalid user_id=%s", sender_id)
    return None


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _call_onebot_action(
    event: AstrMessageEvent,
    action: str,
    params: dict[str, Any],
) -> tuple[bool, Any]:
    bot = _get_bot_client(event)
    if bot is None:
        return False, None

    method = _callable_attr(bot, action)
    if callable(method):
        return True, await _maybe_await(method(**params))

    api = getattr(bot, "api", None)
    call_action = _callable_attr(api, "call_action")
    if callable(call_action):
        return True, await _maybe_await(call_action(action, **params))

    call_action = _callable_attr(bot, "call_action")
    if callable(call_action):
        return True, await _maybe_await(call_action(action, **params))

    return False, None


def _callable_attr(obj: Any, name: str) -> Any | None:
    if obj is None:
        return None
    attr = getattr(obj, name, None)
    return attr if callable(attr) else None


async def _component_to_onebot_message(comp: Any) -> dict[str, Any]:
    if isinstance(comp, Comp.Image):
        return {
            "type": "image",
            "data": {"file": str(getattr(comp, "file", "") or "")},
        }
    if isinstance(comp, Comp.File):
        return await comp.to_dict()

    to_dict = getattr(comp, "to_dict", None)
    if callable(to_dict):
        return await _maybe_await(to_dict())

    return comp.toDict()


def _normalize_onebot_file_uris(value: Any) -> Any:
    """将 OneBot 文件消息中的本地路径转换为可识别的 file URI。"""
    if isinstance(value, list):
        return [_normalize_onebot_file_uris(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize_onebot_file_uris(item) for item in value)
    if not isinstance(value, dict):
        return value

    normalized = {key: _normalize_onebot_file_uris(item) for key, item in value.items()}
    if normalized.get("type") != "file":
        return normalized

    data = normalized.get("data")
    if not isinstance(data, dict):
        return normalized
    file_value = data.get("file")
    if not isinstance(file_value, str) or not file_value or "://" in file_value:
        return normalized

    file_path = Path(file_value)
    if file_path.is_absolute():
        data["file"] = file_path.as_uri()
    return normalized


class SendStrategy(ABC):
    """Abstract base class for send strategies."""

    @abstractmethod
    async def send(
        self,
        event: AstrMessageEvent,
        chain: list[Any],
        auto_revoke: bool = False,
    ) -> bool:
        """Send message chain using this strategy.

        Args:
            event: Message event
            chain: Message chain (list of components)
            auto_revoke: Whether to schedule auto-revoke after send

        Returns:
            True if send succeeded, False otherwise
        """
        ...

    async def send_with_status(
        self,
        event: AstrMessageEvent,
        chain: list[Any],
        auto_revoke: bool = False,
    ) -> SendAttemptResult:
        """Send message chain and expose whether fallback is safe."""
        success = await self.send(event, chain, auto_revoke)
        return SendAttemptResult.success() if success else SendAttemptResult.failed()


class DirectSendStrategy(SendStrategy):
    """Direct send strategy — sends images in a single message chain."""

    def __init__(
        self, plugin_context: Any, *, allow_file_uri_passthrough: bool = False
    ) -> None:
        """Initialize direct send strategy.

        Args:
            plugin_context: Plugin context for sending messages
            allow_file_uri_passthrough: 是否允许可信 file:// 图片通过
                OneBot 原始 action 绕过 AstrBot 的 base64 适配器转换。
        """
        self._context = plugin_context
        self._allow_file_uri_passthrough = allow_file_uri_passthrough

    async def send(
        self,
        event: AstrMessageEvent,
        chain: list[Any],
        auto_revoke: bool = False,
    ) -> bool:
        """Send images directly in message chain.

        Args:
            event: Message event
            chain: Message chain
            auto_revoke: Not supported for direct send (ignored)

        Returns:
            True if send succeeded
        """
        result = await self.send_with_status(event, chain, auto_revoke)
        return result.accepted

    async def send_with_status(
        self,
        event: AstrMessageEvent,
        chain: list[Any],
        auto_revoke: bool = False,
    ) -> SendAttemptResult:
        """Send images directly and keep timeout separate from confirmed failure."""
        try:
            send_result = await self._send_message(event, chain, auto_revoke)

            platform_name = getattr(event.platform, "name", "unknown")

            # AstrBot/OneBot 适配器偶尔会在平台侧已接收消息时返回 None。
            # 这里不把不确定返回当作失败，避免图片仍在延迟送达时误触发回退策略。
            if send_result is None and is_onebot_like_platform(platform_name):
                logger.info(
                    "[send] direct send returned None but treated as pending success: platform=%s, chain=%d",
                    platform_name,
                    len(chain),
                )
                return SendAttemptResult.pending_delivery(
                    "adapter returned no message id"
                )

            message_ids = extract_message_ids(send_result)
            if auto_revoke and not message_ids:
                logger.warning(
                    "[send] direct send accepted without message_id: platform=%s, chain=%d",
                    platform_name,
                    len(chain),
                )
            logger.info(
                "[send] direct send completed: platform=%s, chain=%d, ids=%d",
                platform_name,
                len(chain),
                len(message_ids),
            )
            return SendAttemptResult.success(message_ids)
        except TimeoutError as exc:
            # 发送接口超时后无法判断平台侧是否已经接收消息，重发 fallback 可能造成重复图片。
            logger.warning(
                "[send] direct send confirmation timed out, treating as pending delivery: platform=%s, chain=%d, error=%s",
                getattr(event.platform, "name", "unknown"),
                len(chain),
                exc,
            )
            return SendAttemptResult.pending_delivery("send confirmation timed out")
        except Exception as exc:
            logger.exception(
                "[send] direct send failed: platform=%s, chain=%d, error=%s",
                getattr(event.platform, "name", "unknown"),
                len(chain),
                exc,
            )
            return SendAttemptResult.failed(str(exc))

    async def _send_message(
        self,
        event: AstrMessageEvent,
        chain: list[Any],
        auto_revoke: bool,
    ) -> Any:
        if self._requires_onebot_passthrough(event, chain, auto_revoke):
            attempted, send_result = await self._send_onebot_message_chain(event, chain)
            if attempted:
                return send_result
        result = event.chain_result(chain)
        return await self._context.send_message(event.unified_msg_origin, result)

    def _requires_onebot_passthrough(
        self, event: AstrMessageEvent, chain: list[Any], auto_revoke: bool
    ) -> bool:
        platform_name = getattr(getattr(event, "platform", None), "name", "") or ""
        if not is_onebot_like_platform(platform_name):
            return False
        if auto_revoke and any(
            self._is_revoke_capable_component(comp) for comp in chain
        ):
            return True
        return any(
            self._is_onebot_image_ref(comp)
            for comp in chain
            if isinstance(comp, Comp.Image)
        )

    def _is_revoke_capable_component(self, comp: Any) -> bool:
        return isinstance(comp, Comp.Image | Comp.File | Comp.Plain)

    def _is_onebot_image_ref(self, comp: Comp.Image) -> bool:
        file_value = getattr(comp, "file", None)
        if not isinstance(file_value, str) or "://" not in file_value:
            return False
        if file_value.startswith("file://"):
            return self._allow_file_uri_passthrough
        return not (
            file_value.startswith("http://")
            or file_value.startswith("https://")
            or file_value.startswith("base64://")
        )

    async def _send_onebot_message_chain(
        self, event: AstrMessageEvent, chain: list[Any]
    ) -> tuple[bool, Any]:
        target = _onebot_target(event)
        if target is None:
            return False, None

        target_type, target_id = target
        # 需要自动撤回时在发送阶段直接取得可恢复撤回所需的 message_id；
        # 普通文件消息与图片消息都走同一条 OneBot action 链路。
        message: list[dict[str, Any]] = []
        for comp in chain:
            message.append(await _component_to_onebot_message(comp))
        # 本子现在以普通 File 直发；本地路径需要转换为 file://，否则
        # NapCat 可能返回消息 ID，但客户端打开附件时会显示下载失败。
        message = _normalize_onebot_file_uris(message)

        if target_type == "group":
            return await _call_onebot_action(
                event,
                "send_group_msg",
                {"group_id": target_id, "message": message},
            )
        return await _call_onebot_action(
            event,
            "send_private_msg",
            {"user_id": target_id, "message": message},
        )


class ForwardSendStrategy(SendStrategy):
    """Forward send strategy — uses merge forward (OneBot v11)."""

    def __init__(self, plugin_context: Any) -> None:
        """Initialize forward send strategy.

        Args:
            plugin_context: Plugin context for sending messages
        """
        self._context = plugin_context

    async def send(
        self,
        event: AstrMessageEvent,
        chain: list[Any],
        auto_revoke: bool = False,
    ) -> bool:
        """Send images using merge forward.

        Args:
            event: Message event
            chain: Message chain (list of image components)
            auto_revoke: Not supported (handled by caller)

        Returns:
            True if send succeeded
        """
        result = await self.send_with_status(event, chain, auto_revoke)
        return result.accepted

    async def send_with_status(
        self,
        event: AstrMessageEvent,
        chain: list[Any],
        auto_revoke: bool = False,
    ) -> SendAttemptResult:
        """Send forward nodes and keep adapter ack timeout from triggering fallback."""
        import time

        build_start = time.monotonic()
        nodes = []
        uin = event.get_self_id()
        if not uin:
            logger.warning(
                "[forward] get_self_id() returned empty, forward nodes may be rejected by platform"
            )
            uin = ""  # 保持空字符串而非 None,避免序列化报错
        for comp in chain:
            if isinstance(comp, Comp.Image):
                node = Comp.Node(
                    uin=uin,
                    name="色图",
                    content=[comp],
                )
                nodes.append(node)

        build_end = time.monotonic()
        logger.debug(
            "[forward] built nodes: count=%d, elapsed=%.3fs",
            len(nodes),
            build_end - build_start,
        )

        return await self._send_nodes_direct_with_status(event, nodes, auto_revoke)

    async def _send_nodes_direct_with_status(
        self,
        event: AstrMessageEvent,
        nodes: list[Comp.Node],
        auto_revoke: bool = False,
    ) -> SendAttemptResult:
        """Send forward nodes and expose whether fallback is safe."""
        try:
            platform_name = getattr(getattr(event, "platform", None), "name", "")
            if auto_revoke and is_onebot_like_platform(platform_name):
                attempted, raw_result = await self._send_nodes_raw(event, nodes)
                if attempted:
                    if raw_result is None:
                        logger.warning(
                            "[forward] raw send returned no response; treating as pending"
                        )
                        return SendAttemptResult.pending_delivery(
                            "forward adapter returned no message id"
                        )
                    message_ids = extract_message_ids(raw_result)
                    if not message_ids:
                        logger.warning(
                            "[forward] raw send accepted without message_id: nodes=%d",
                            len(nodes),
                        )
                    logger.info(
                        "[forward] raw send completed: nodes=%d, ids=%d",
                        len(nodes),
                        len(message_ids),
                    )
                    return SendAttemptResult.success(message_ids)

            # AstrBot 当前版本用 Node/Nodes 作为待发送合并转发内容；
            # Forward 只表示已收到的转发消息引用，不能包装 Node 发送。
            forward_chain = [Comp.Nodes(nodes)]
            result = event.chain_result(forward_chain)
            send_result = await self._context.send_message(
                event.unified_msg_origin, result
            )

            logger.info("[forward] send completed: nodes=%d", len(nodes))
            return SendAttemptResult.success(extract_message_ids(send_result))
        except TimeoutError as exc:
            # 合并转发也可能在平台侧已接收后只丢失本地确认，立刻 fallback 会造成重复消息。
            logger.warning(
                "[forward] send confirmation timed out, treating as pending delivery: nodes=%d, error=%s",
                len(nodes),
                exc,
            )
            return SendAttemptResult.pending_delivery("forward confirmation timed out")
        except Exception as exc:
            logger.exception(
                "[forward] send failed: nodes=%d, error=%s",
                len(nodes),
                exc,
            )
            return SendAttemptResult.failed(str(exc))

    async def _send_nodes_raw(
        self, event: AstrMessageEvent, nodes: list[Comp.Node]
    ) -> tuple[bool, Any]:
        target = _onebot_target(event)
        if target is None:
            return False, None

        payload = await Comp.Nodes(nodes).to_dict()
        messages = payload.get("messages", [])
        target_type, target_id = target
        if target_type == "group":
            return await _call_onebot_action(
                event,
                "send_group_forward_msg",
                {"group_id": target_id, "messages": messages},
            )
        return await _call_onebot_action(
            event,
            "send_private_forward_msg",
            {"user_id": target_id, "messages": messages},
        )


def resolve_send_mode(
    send_mode: str,
    image_count: int,
    supports_forward: bool = True,
) -> str:
    """Resolve effective send mode.

    Args:
        send_mode: Configured send mode (image/forward/auto)
        image_count: Number of images to send
        supports_forward: Whether platform supports forward

    Returns:
        Effective send mode (image or forward)
    """
    if send_mode == "auto":
        # 仅在平台支持合并转发(当前为 OneBot/aiocqhttp 类)且图片多于 1 张时
        # 走 forward 绕开 NTQQ 单条 8 张限制;否则退回直发。
        if image_count > 1 and supports_forward:
            return "forward"
        return "image"
    if send_mode == "forward" and not supports_forward:
        return "image"
    return send_mode
