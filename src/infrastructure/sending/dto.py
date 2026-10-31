"""Infrastructure DTOs for sending strategies."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class SendOptions:
    """Value object for send strategy options."""

    send_mode: str
    auto_revoke: bool
    revoke_delay: int
    r18_docx_mode: bool
    auto_revoke_scope: str = "none"
    napcat_stream_mode: str = "fallback"
    napcat_stream_chunk_kb: int = 64
    napcat_local_file_mode: str = "disabled"
    napcat_local_file_allowed_roots: tuple[str, ...] = ()
    compress_enabled: bool = False
    compress_max_mb: int = 4


@dataclass(frozen=True)
class SendAttemptResult:
    """单次发送尝试的结果，区分确认失败和平台确认超时。"""

    accepted: bool
    pending: bool = False
    reason: str = ""
    message_ids: tuple[str, ...] = ()

    @classmethod
    def success(cls, message_ids: str | Iterable[object] = ()) -> "SendAttemptResult":
        """发送链路已确认成功。"""
        return cls(accepted=True, message_ids=_normalize_message_ids(message_ids))

    @classmethod
    def pending_delivery(
        cls, reason: str, message_ids: str | Iterable[object] = ()
    ) -> "SendAttemptResult":
        """平台侧可能已接收，但本地未拿到最终确认。"""
        return cls(
            accepted=True,
            pending=True,
            reason=reason,
            message_ids=_normalize_message_ids(message_ids),
        )

    @classmethod
    def failed(cls, reason: str = "") -> "SendAttemptResult":
        """发送链路已确认失败，可以进入后续 fallback。"""
        return cls(accepted=False, reason=reason)


def _normalize_message_ids(message_ids: str | Iterable[object]) -> tuple[str, ...]:
    """Normalize message ids without treating one string id as a character list."""
    items = (message_ids,) if isinstance(message_ids, str) else message_ids
    normalized: list[str] = []
    for item in items:
        text = str(item).strip()
        if text:
            normalized.append(text)
    return tuple(normalized)
